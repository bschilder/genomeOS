"""Offline B0 benchmark runner integration (design §§ 5, 7, 8; #189)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from genomeos.validation.baseline import fit_pooled_b0
from genomeos.validation.benchmark import validate_allele_observations

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "benchmark_allele_frequency.py"
FIXTURES = ROOT / "tests" / "fixtures" / "benchmark"


def _command(out: Path, *, observations: Path | None = None, assignments: Path | None = None):
    return [
        sys.executable,
        str(SCRIPT),
        "--observations",
        str(observations or FIXTURES / "observations.tsv"),
        "--assignments",
        str(assignments or FIXTURES / "assignments.tsv"),
        "--dependencies",
        str(FIXTURES / "dependencies.tsv"),
        "--data-version",
        "fixture-v1",
        "--prior-alpha",
        "1.0",
        "--prior-beta",
        "1.0",
        "--buffer-km",
        "300",
        "--posterior-draws",
        "64",
        "--seed",
        "42",
        "--evidence-kind",
        "synthetic_fixture",
        "--out",
        str(out),
    ]


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text())


def _read_observations(path: Path) -> pd.DataFrame:
    raw_string_columns = {
        column: str
        for column in (
            "variant_id",
            "rsid",
            "population_id",
            "ac",
            "an",
            "source_record_id",
            "source",
            "assay",
            "date_lower",
            "date_upper",
            "sampling_design",
            "cohort_id",
            "ingest_version",
        )
    }
    return validate_allele_observations(
        pd.read_csv(path, sep="\t", dtype=raw_string_columns, keep_default_na=False)
    )


def test_successful_runner_writes_explicit_b0_nonpublication_record(tmp_path):
    output = tmp_path / "run"

    completed = _run(_command(output))

    assert completed.returncode == 0, completed.stderr
    assert sorted(path.name for path in output.iterdir()) == [
        "fold_status.tsv",
        "inventory.json",
        "manifest.json",
        "predictions.tsv",
        "summary.json",
    ]
    manifest = _json(output / "manifest.json")
    assert manifest["model"] == {
        "model_id": "B0",
        "name": "per_variant_pooled_beta_posterior_binomial_count_model",
        "resident_calibrated": False,
        "survey_heterogeneity_model": False,
    }
    assert manifest["evidence_kind"] == "synthetic_fixture"
    assert manifest["publication_eligible"] is False
    assert manifest["configuration"] == {
        "buffer_km": 300.0,
        "data_version": "fixture-v1",
        "posterior_draws": 64,
        "prior_alpha": 1.0,
        "prior_beta": 1.0,
        "seed": 42,
    }
    assert len(manifest["code_revision"]) == 40
    assert len(manifest["configuration_sha256"]) == 64
    assert len(manifest["inputs_sha256"]) == 64
    assert len(manifest["split_manifest_sha256"]) == 64
    assert set(manifest["science_source_sha256"]) == {
        "genomeos/observations/schema.py",
        "genomeos/validation/baseline.py",
        "genomeos/validation/benchmark.py",
        "genomeos/validation/predictive.py",
        "genomeos/validation/splits.py",
        "scripts/benchmark_allele_frequency.py",
    }
    assert all(fold["posterior_seed"] != fold["predictive_seed"] for fold in manifest["splits"])
    assert {fold["status"] for fold in manifest["splits"]} == {"completed"}

    inventory = _json(output / "inventory.json")
    assert inventory["zero_count_count"] == 1
    assert inventory["date_unspecified_modern_count"] == 4
    predictions = pd.read_csv(output / "predictions.tsv", sep="\t", keep_default_na=False)
    assert len(predictions) == 4
    assert set(predictions["observed_ac"]) == {0, 2, 8, 10}
    seeds_by_split = {fold["split_id"]: fold for fold in manifest["splits"]}
    assert all(
        row.predictive_seed == seeds_by_split[row.split_id]["predictive_seed"]
        and row.posterior_draw_seed == seeds_by_split[row.split_id]["posterior_seed"]
        for row in predictions.itertuples(index=False)
    )
    summary = _json(output / "summary.json")
    assert summary["model_id"] == "B0"
    assert summary["publication_eligible"] is False
    assert summary["benchmark"]["comparison_complete"] is True


def test_outputs_are_byte_reproducible_across_new_output_directories(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_run = _run(_command(first))
    second_run = _run(_command(second))

    assert first_run.returncode == second_run.returncode == 0
    assert {path.name: path.read_bytes() for path in first.iterdir()} == {
        path.name: path.read_bytes() for path in second.iterdir()
    }


def test_pooled_fit_uses_training_counts_only_and_shares_variant_draws():
    observations = _read_observations(FIXTURES / "observations.tsv")
    training = observations[observations["source_record_id"].str.startswith("east")]
    testing = observations[observations["source_record_id"].str.startswith("west")]
    repeated = testing.iloc[[0]].copy()
    repeated.loc[:, "source_record_id"] = "west-v1-repeat"
    repeated.loc[:, "cohort_id"] = "cohort-west-repeat"
    testing = pd.concat([testing, repeated], ignore_index=True)
    changed_test = testing.copy()
    changed_test.loc[:, "ac"] = [19, 1, 5]

    original = fit_pooled_b0(
        training,
        testing,
        prior_alpha=1.0,
        prior_beta=1.0,
        posterior_draws=64,
        seed=123,
    )
    changed = fit_pooled_b0(
        training,
        changed_test,
        prior_alpha=1.0,
        prior_beta=1.0,
        posterior_draws=64,
        seed=123,
    )

    assert original.posteriors == changed.posteriors
    assert [
        (
            posterior.variant_id,
            posterior.training_observation_count,
            posterior.training_ac,
            posterior.training_an,
            posterior.alpha,
            posterior.beta,
        )
        for posterior in original.posteriors
    ] == [
        ("chr1-100-A-G", 1, 2, 20, 3.0, 19.0),
        ("chr2-200-C-T", 1, 10, 20, 11.0, 11.0),
    ]
    assert (original.predictive.mean_draws == changed.predictive.mean_draws).all()
    for variant in testing["variant_id"].unique():
        positions = testing["variant_id"].to_numpy() == variant
        if positions.sum() > 1:
            variant_draws = original.predictive.mean_draws[:, positions]
            assert (variant_draws == variant_draws[:, :1]).all()


def test_optional_seed_and_draw_defaults_are_reported(tmp_path):
    command = _command(tmp_path / "run")
    for option in ("--seed", "--posterior-draws"):
        index = command.index(option)
        del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode == 0, completed.stderr
    configuration = _json(tmp_path / "run" / "manifest.json")["configuration"]
    assert configuration["seed"] == 42
    assert configuration["posterior_draws"] == 2048


@pytest.mark.parametrize("missing_option", ["--data-version", "--prior-alpha", "--evidence-kind"])
def test_required_scientific_metadata_cannot_be_omitted(tmp_path, missing_option):
    command = _command(tmp_path / "run")
    index = command.index(missing_option)
    del command[index : index + 2]

    completed = _run(command)

    assert completed.returncode != 0
    assert missing_option in completed.stderr


def test_fractional_raw_count_token_is_refused_before_binary_float_rounding(tmp_path):
    observations = (FIXTURES / "observations.tsv").read_text().replace(
        "\t0\t20\twest-v1", "\t12.000000000000000001\t20\twest-v1", 1
    )
    source = tmp_path / "fractional.tsv"
    source.write_text(observations)

    completed = _run(_command(tmp_path / "run", observations=source))

    assert completed.returncode != 0
    assert "ac must not contain fractional values" in completed.stderr
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("chr1-100-A-G", "phenotype:enzyme-deficiency", "phenotype-prefixed"),
        ("\t0\t0\tpopulation_random", "\t0\t10\tpopulation_random", "zero date bounds"),
    ],
)
def test_runner_refuses_phenotype_or_nonzero_date_rows(tmp_path, old, new, message):
    source = tmp_path / "unsupported.tsv"
    source.write_text((FIXTURES / "observations.tsv").read_text().replace(old, new, 1))

    completed = _run(_command(tmp_path / "run", observations=source))

    assert completed.returncode != 0
    assert message in completed.stderr
    assert not (tmp_path / "run").exists()


@pytest.mark.parametrize("kind", ["orphan", "inconsistent_group", "dependency_orphan"])
def test_auxiliary_identifiers_and_variant_groups_are_validated(tmp_path, kind):
    assignments = pd.read_csv(FIXTURES / "assignments.tsv", sep="\t", dtype=str)
    dependencies = FIXTURES / "dependencies.tsv"
    if kind == "orphan":
        assignments.loc[0, "source_record_id"] = "unknown"
    elif kind == "inconsistent_group":
        assignments.loc[0, "variant_group"] = "different"
    else:
        dependencies = tmp_path / "dependencies.tsv"
        dependencies.write_text("source_record_id_a\tsource_record_id_b\nwest-v1\tunknown\n")
    assignment_path = tmp_path / "assignments.tsv"
    assignments.to_csv(assignment_path, sep="\t", index=False)
    command = _command(tmp_path / "run", assignments=assignment_path)
    command[command.index("--dependencies") + 1] = str(dependencies)

    completed = _run(command)

    assert completed.returncode != 0
    assert not (tmp_path / "run").exists()


def test_preexisting_output_directory_is_refused_without_overwrite(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("untouched")

    completed = _run(_command(output))

    assert completed.returncode != 0
    assert "already exists" in completed.stderr
    assert marker.read_text() == "untouched"


def test_infeasible_folds_are_written_and_cause_nonzero_exit(tmp_path):
    output = tmp_path / "infeasible"

    completed = _run(
        _command(
            output,
            observations=FIXTURES / "infeasible_observations.tsv",
            assignments=FIXTURES / "infeasible_assignments.tsv",
        )
    )

    assert completed.returncode != 0
    statuses = pd.read_csv(output / "fold_status.tsv", sep="\t", keep_default_na=False)
    assert set(statuses["status"]) == {"infeasible"}
    assert all("absent from training" in reason for reason in statuses["failure_reason"])
    assert pd.read_csv(output / "predictions.tsv", sep="\t").empty
    summary = _json(output / "summary.json")
    assert summary["benchmark"]["comparison_complete"] is False
    assert summary["benchmark"]["split_counts"]["infeasible"] == 2
    assert {fold["status"] for fold in _json(output / "manifest.json")["splits"]} == {
        "infeasible"
    }


def test_fitting_failures_are_written_and_cause_nonzero_exit(tmp_path):
    output = tmp_path / "failed"
    command = _command(output)
    command[command.index("--prior-alpha") + 1] = "1e308"
    command[command.index("--prior-beta") + 1] = "1e308"

    completed = _run(command)

    assert completed.returncode != 0
    statuses = pd.read_csv(output / "fold_status.tsv", sep="\t", keep_default_na=False)
    assert set(statuses["status"]) == {"failed"}
    assert all("stable numeric domain" in reason for reason in statuses["failure_reason"])
    manifest = _json(output / "manifest.json")
    assert {fold["status"] for fold in manifest["splits"]} == {"failed"}
    assert _json(output / "summary.json")["benchmark"]["split_counts"]["failed"] == 2

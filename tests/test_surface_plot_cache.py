"""Plot-cache alignment tests for pointwise prior normalization (design §7.1b)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts import plot_surface
from scripts.plot_surface import read_prediction_cache, write_prediction_cache


def _payload():
    return {
        "h3_index": np.array(["84754a9ffffffff", "8482e9dffffffff"]),
        "lat": np.array([0.1, 1.2]),
        "lon": np.array([2.3, 3.4]),
        "central": np.array([0.10000000000000002, 0.2]),
        "sd": np.array([0.03, 0.04]),
        "prior_sd": np.array([0.05000000000000001, 0.08]),
        "range_km": 1000.125,
        "prior_seed": 42,
    }


def test_plot_cache_round_trips_exact_ordered_grid_and_local_prior(tmp_path):
    values = _payload()
    path = tmp_path / "predictions.npz"
    write_prediction_cache(path, **values)
    restored = read_prediction_cache(
        path,
        h3_index=values["h3_index"],
        lat=values["lat"],
        lon=values["lon"],
        prior_seed=42,
    )
    np.testing.assert_array_equal(restored["prior_sd"], values["prior_sd"])
    np.testing.assert_array_equal(restored["central"], values["central"])
    assert restored["range_km"] == values["range_km"]


def test_plot_cache_refuses_legacy_and_changed_equal_length_grid(tmp_path):
    values = _payload()
    legacy = tmp_path / "legacy.npz"
    np.savez(legacy, central=values["central"], sd=values["sd"], prior_sd=0.1, range_km=1.0)
    with pytest.raises(ValueError, match="new cache path"):
        read_prediction_cache(
            legacy,
            h3_index=values["h3_index"],
            lat=values["lat"],
            lon=values["lon"],
            prior_seed=42,
        )

    current = tmp_path / "current.npz"
    write_prediction_cache(current, **values)
    with pytest.raises(ValueError, match="identit|coordinate|grid"):
        read_prediction_cache(
            current,
            h3_index=values["h3_index"][::-1],
            lat=values["lat"][::-1],
            lon=values["lon"][::-1],
            prior_seed=42,
        )


def test_plot_cache_refuses_malformed_prior_and_overwrite(tmp_path):
    values = _payload()
    path = tmp_path / "predictions.npz"
    bad = {**values, "prior_sd": np.array([0.05, np.nan])}
    with pytest.raises(ValueError, match="prior"):
        write_prediction_cache(path, **bad)
    write_prediction_cache(path, **values)
    with pytest.raises(FileExistsError, match="new cache path"):
        write_prediction_cache(path, **values)


def test_suffixless_plot_cache_writes_exact_path_without_overwriting_npz_alias(tmp_path):
    values = _payload()
    requested = tmp_path / "predictions"
    npz_alias = tmp_path / "predictions.npz"
    np.savez(npz_alias, sentinel=np.array([123.0]))
    before = npz_alias.read_bytes()

    assert write_prediction_cache(requested, **values) == requested
    assert requested.is_file()
    assert npz_alias.read_bytes() == before
    with pytest.raises(FileExistsError, match="new cache path"):
        write_prediction_cache(requested, **values)


def test_cache_only_reuse_accepts_the_valid_stored_seed(tmp_path):
    values = {**_payload(), "prior_seed": 7}
    path = tmp_path / "predictions.npz"
    write_prediction_cache(path, **values)

    restored = read_prediction_cache(
        path,
        h3_index=values["h3_index"],
        lat=values["lat"],
        lon=values["lon"],
    )
    assert restored["prior_seed"] == 7


def test_cli_checks_cached_predictions_against_nondefault_saved_fit_seed(
    tmp_path, monkeypatch
):
    cache = tmp_path / "predictions.npz"
    cache.touch()
    fit_path = tmp_path / "surface.fit.pkl"
    fit_path.touch()
    captured = {}

    class StopAfterCacheRead(Exception):
        pass

    def read_cache(*args, **kwargs):
        captured["prior_seed"] = kwargs["prior_seed"]
        raise StopAfterCacheRead

    observations = pd.DataFrame({"lat": [0.0], "lon": [0.0], "ac": [1], "an": [10]})
    monkeypatch.setattr(plot_surface.map_surveys, "load", lambda *args: (observations, "fixture"))
    monkeypatch.setattr(plot_surface, "h3_land_cells", lambda resolution: ["83754efffffffff"])
    monkeypatch.setattr(plot_surface, "h3_polygons", lambda cells: ([], np.array([0])))
    monkeypatch.setattr(
        plot_surface, "load_fit", lambda path: SimpleNamespace(config=SimpleNamespace(seed=7))
    )
    monkeypatch.setattr(plot_surface, "read_prediction_cache", read_cache)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "plot_surface.py",
            "--observations", str(tmp_path / "observations.csv"),
            "--out", str(tmp_path / "surface.png"),
            "--fit", str(fit_path),
            "--cache", str(cache),
        ],
    )

    with pytest.raises(StopAfterCacheRead):
        plot_surface.main()
    assert captured["prior_seed"] == 7


@pytest.mark.parametrize("field,value", [("prior_draws", 499), ("prior_normalization", "scalar")])
def test_plot_cache_refuses_wrong_protocol_metadata(tmp_path, field, value):
    values = _payload()
    path = tmp_path / "predictions.npz"
    write_prediction_cache(path, **values)
    with np.load(path, allow_pickle=False) as cached:
        payload = {name: cached[name] for name in cached.files}
    payload[field] = value
    np.savez(path, **payload)
    with pytest.raises(ValueError, match="new cache path"):
        read_prediction_cache(
            path,
            h3_index=values["h3_index"],
            lat=values["lat"],
            lon=values["lon"],
            prior_seed=42,
        )


@pytest.mark.parametrize("bad_format", [2.9, 2.0, "2", True])
def test_plot_cache_refuses_noninteger_or_boolean_format(tmp_path, bad_format):
    values = _payload()
    path = tmp_path / "predictions.npz"
    write_prediction_cache(path, **values)
    with np.load(path, allow_pickle=False) as cached:
        payload = {name: cached[name] for name in cached.files}
    payload["cache_format"] = bad_format
    np.savez(path, **payload)

    with pytest.raises(ValueError, match="new cache path"):
        read_prediction_cache(
            path,
            h3_index=values["h3_index"],
            lat=values["lat"],
            lon=values["lon"],
            prior_seed=42,
        )

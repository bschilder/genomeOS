"""B0H source/distribution provenance tests (design §§5, 7–8, 12)."""

from __future__ import annotations

import hashlib
import importlib.metadata
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import reference_b0h_provenance as subject

ROOT = Path(__file__).resolve().parents[1]


def test_source_hashes_cover_consumed_modules_and_self():
    hashes = subject.b0h_source_hashes(ROOT, cdf_backend="scipy")
    assert set(hashes) == {
        "genomeos/surfaces/heterogeneity_types.py",
        "genomeos/surfaces/reference_heterogeneity.py",
        "genomeos/surfaces/heterogeneity_likelihood.py",
        "genomeos/validation/reference_b0h_fold.py",
        "genomeos/validation/reference_b0h_artifacts.py",
        "scripts/reference_b0h_provenance.py",
    }
    for relative, digest in hashes.items():
        assert digest == hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def test_wrong_source_origin_is_refused(monkeypatch, tmp_path):
    real = subject.importlib.import_module

    def wrong(name):
        if name == "genomeos.surfaces.heterogeneity_types":
            return SimpleNamespace(__file__=str(tmp_path / "lookalike.py"))
        return real(name)

    monkeypatch.setattr(subject.importlib, "import_module", wrong)
    with pytest.raises(ValueError, match="outside this checkout"):
        subject.b0h_source_hashes(ROOT, cdf_backend="scipy")


def test_required_versions_and_missing_distribution(monkeypatch):
    monkeypatch.setattr(subject.importlib.metadata, "version", lambda name: "synthetic-version")
    versions = subject.b0h_package_versions(cdf_backend="scipy")
    assert set(versions) == {"pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib"}
    assert set(versions.values()) == {"synthetic-version"}

    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(subject.importlib.metadata, "version", missing)
    with pytest.raises(importlib.metadata.PackageNotFoundError):
        subject.b0h_package_versions(cdf_backend="scipy")


def test_runtime_has_no_inferred_backend_evidence(monkeypatch):
    monkeypatch.setattr(subject.platform, "python_version", lambda: "3.12.synthetic")
    assert subject.b0h_runtime() == {
        "python_version": {"status": "available", "value": "3.12.synthetic", "reason": None},
        "jax_backend": {"status": "unavailable", "value": None,
                        "reason": "Public fit results do not expose JAX execution placement."},
        "cdf_backend": {"status": "unavailable", "value": None,
                        "reason": "Public scoring results do not expose CDF execution placement."},
    }


def test_cupy_distribution_owner_is_established(monkeypatch, tmp_path):
    origin = tmp_path / "cupy" / "__init__.py"
    file = Path("cupy/__init__.py")
    distribution = SimpleNamespace(
        files=[file], version="synthetic-cuda-version",
        locate_file=lambda value: tmp_path / value,
    )
    monkeypatch.setattr(subject.importlib.util, "find_spec", lambda name: SimpleNamespace(origin=str(origin)))
    monkeypatch.setattr(subject.importlib.metadata, "packages_distributions",
                        lambda: {"cupy": ["cupy-cuda12x"]})
    monkeypatch.setattr(subject.importlib.metadata, "distribution", lambda name: distribution)
    monkeypatch.setattr(subject.importlib.metadata, "version", lambda name: "synthetic-version")
    assert subject.b0h_package_versions(cdf_backend="cupy")["cupy"] == "synthetic-cuda-version"
    monkeypatch.setattr(subject.importlib.metadata, "packages_distributions", lambda: {})
    with pytest.raises(ValueError, match="one distribution"):
        subject.b0h_package_versions(cdf_backend="cupy")

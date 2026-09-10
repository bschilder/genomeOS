"""B0H local source/runtime provenance (design §§5, 7–8, 12; integration §4)."""

from __future__ import annotations

import hashlib
import importlib
import importlib.metadata
import importlib.util
import platform
from pathlib import Path


def b0h_source_hashes(root: Path, *, cdf_backend: str) -> dict[str, str]:
    """Hash imported B0H modules only after verifying their checkout origins."""
    names = [
        "genomeos.surfaces.heterogeneity_types",
        "genomeos.surfaces.reference_heterogeneity",
        "genomeos.surfaces.heterogeneity_likelihood",
        "genomeos.validation.reference_b0h_fold",
        "genomeos.validation.reference_b0h_artifacts",
    ]
    if cdf_backend == "cupy":
        names.append("genomeos.validation.predictive_cupy")
    result = {}
    for name in names:
        relative = name.replace(".", "/") + ".py"
        actual = Path(importlib.import_module(name).__file__).resolve()
        if actual != (root / relative).resolve():
            raise ValueError(f"imported source {relative} resolved outside this checkout")
        result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    relative = "scripts/reference_b0h_provenance.py"
    actual = Path(__file__).resolve()
    if actual != (root / relative).resolve():
        raise ValueError(f"imported source {relative} resolved outside this checkout")
    result[relative] = hashlib.sha256(actual.read_bytes()).hexdigest()
    return result


def _cupy_version() -> str:
    specification = importlib.util.find_spec("cupy")
    if specification is None or specification.origin is None:
        raise ModuleNotFoundError("selected CuPy package is unavailable")
    origin = Path(specification.origin).resolve()
    owners = []
    for name in importlib.metadata.packages_distributions().get("cupy", []):
        distribution = importlib.metadata.distribution(name)
        if any(Path(distribution.locate_file(file)).resolve() == origin
               for file in distribution.files or ()):
            owners.append(distribution)
    if len(owners) != 1:
        raise ValueError("CuPy package origin must be owned by exactly one distribution")
    return owners[0].version


def b0h_package_versions(*, cdf_backend: str) -> dict[str, str]:
    """Require installed distribution provenance, including selected CuPy ownership."""
    result = {name: importlib.metadata.version(name)
              for name in ("pymc", "pytensor", "arviz", "xarray", "numpyro", "jax", "jaxlib")}
    if cdf_backend == "cupy":
        result["cupy"] = _cupy_version()
    if any(not isinstance(value, str) or not value.strip() for value in result.values()):
        raise ValueError("required distribution versions must be nonempty")
    return result


def b0h_runtime() -> dict[str, dict[str, str | None]]:
    """Report observed Python and unavailable public execution-placement evidence."""
    version = platform.python_version()
    if not version:
        raise ValueError("Python version observation is unavailable")
    return {
        "python_version": {"status": "available", "value": version, "reason": None},
        "jax_backend": {"status": "unavailable", "value": None,
                        "reason": "Public fit results do not expose JAX execution placement."},
        "cdf_backend": {"status": "unavailable", "value": None,
                        "reason": "Public scoring results do not expose CDF execution placement."},
    }

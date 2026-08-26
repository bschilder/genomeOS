"""Report the environment, and empirically test how sampler options reach NUTS.

    python scripts/env_report.py

Two jobs, both aimed at settling disagreements about behaviour rather than versions.

**1. What is installed.** `pyproject.toml` carries lower bounds (`pymc>=5.16`), not pins, so two
contributors following the documented install can be a major version apart — and PyMC changed how
NUTS options are passed between 5.x and 6.x. `requirements.lock` exists to remove that variable;
this prints what is actually loaded, which is the thing that decides behaviour.

**2. Where a sampler option actually lands.** `pm.sample` accepts NUTS options through more than
one channel, and which one works depends on the version. Rather than reasoning from source, this
spies on `sample_jax_nuts` and reports what each channel really delivers in *this* environment.
Anyone can run it and compare, which turns "your claim is wrong" into "we are on different
versions" — usually the truth.
"""

from __future__ import annotations

import importlib.metadata as metadata
import platform
import warnings
from unittest import mock

PACKAGES = (
    "pymc", "pytensor", "numpyro", "jax", "jaxlib", "arviz",
    "numpy", "scipy", "pandas", "pandera", "pyarrow", "h3",
)


def versions() -> None:
    print("=== environment ===")
    print(f"  python   {platform.python_version()}  ({platform.machine()}, {platform.system()})")
    for name in PACKAGES:
        try:
            print(f"  {name:10s} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            print(f"  {name:10s} (not installed)")


def channel_probe() -> None:
    """Pass NUTS options both ways and report what reaches the sampler."""
    import numpy as np
    import pymc as pm
    import pymc.sampling.jax as pymc_jax

    captured: dict[str, object] = {}

    def spy(*_args, **kwargs):
        captured.update(kwargs)
        raise RuntimeError("reached sample_jax_nuts")

    def tiny() -> pm.Model:
        with pm.Model() as model:
            x = pm.Normal("x", 0.0, 1.0)
            pm.Normal("y", x, 1.0, observed=np.array([0.1, 0.2]))
        return model

    channels = {
        'nuts={"chain_method": "vectorized"}': {"nuts": {"chain_method": "vectorized"}},
        'nuts_sampler_kwargs={"chain_method": "vectorized"}': {
            "nuts_sampler_kwargs": {"chain_method": "vectorized"}
        },
    }
    print("\n=== how sampler options reach sample_jax_nuts, in THIS environment ===")
    for label, extra in channels.items():
        captured.clear()
        with mock.patch.object(pymc_jax, "sample_jax_nuts", side_effect=spy):
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                try:
                    with tiny():
                        pm.sample(
                            draws=5, tune=5, chains=2, nuts_sampler="numpyro",
                            progressbar=False, target_accept=0.9, **extra,
                        )
                except RuntimeError:
                    pass
                except Exception as error:  # noqa: BLE001 - a rejected channel is a result
                    print(f"\n  {label}\n    REJECTED: {type(error).__name__}: {error}")
                    continue
                deprecations = [
                    str(w.message)[:88]
                    for w in caught
                    if "deprecat" in str(w.message).lower()
                ]
        print(f"\n  {label}")
        print(f"    chain_method  -> {captured.get('chain_method')!r}")
        print(f"    target_accept -> {captured.get('target_accept')!r}")
        print(f"    deprecation   -> {deprecations[0] if deprecations else 'none'}")


def main() -> None:
    versions()
    try:
        channel_probe()
    except ImportError as error:
        print(f"\n  sampler probe skipped: {error}")
    print(
        "\nTo reproduce this environment exactly:\n"
        "  uv venv --python 3.12 && source .venv/bin/activate\n"
        "  uv pip install -r requirements.lock\n"
        "  python -m pip install -e '.' --no-deps"
    )


if __name__ == "__main__":
    main()

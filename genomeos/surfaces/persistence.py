"""Persist and reload a trained surface (design §5, §6).

Split out of `surfaces.fit` when that module reached the agent-readable budget. The seam is a
real one: fitting is science and serialisation is plumbing, and the plumbing carries caveats —
environment coupling, arbitrary code execution on load — that have nothing to do with the model.

`fit` re-exports both functions, so the nine call sites that already import them from there
continue to work; this module is where they now live.
"""

from __future__ import annotations

from pathlib import Path

from genomeos.surfaces.fit import SurfaceFit

#: Bumped whenever `SurfaceFit`'s fields change in a way that makes an older file unreadable.
FIT_FORMAT = 1


def save_fit(fit: SurfaceFit, path: str | Path) -> Path:
    """Persist a trained surface so predictions cost seconds instead of a refit.

    `SurfaceFit.predict` runs `sample_posterior_predictive` against a live PyMC model, so the
    model object and the posterior have to travel together — writing the InferenceData alone
    would leave nothing able to use it. cloudpickle handles the PyMC/pytensor graph that plain
    `pickle` cannot.

    Two limits worth knowing. The file is **coupled to this environment**: a PyMC or pytensor
    upgrade can make it unreadable, so it is a cache, never an archival artifact — §6 artifacts
    are the parquet outputs, not this. And pickle executes arbitrary code on load, so only ever
    load files you produced yourself.
    """
    import cloudpickle

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        cloudpickle.dump({"format": FIT_FORMAT, "fit": fit}, stream)
    return path


def load_fit(path: str | Path) -> SurfaceFit:
    """Reload a surface written by `save_fit`. See its warning about trust and versioning."""
    import cloudpickle

    with Path(path).open("rb") as stream:
        payload = cloudpickle.load(stream)
    if not isinstance(payload, dict) or payload.get("format") != FIT_FORMAT:
        raise ValueError(
            f"{path} is not a surface fit of format {FIT_FORMAT}; refit rather than guessing at it"
        )
    return payload["fit"]

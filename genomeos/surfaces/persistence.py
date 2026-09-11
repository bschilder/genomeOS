"""Persist and reload a trained surface (design §5, §6).

Split out of `surfaces.fit` when that module reached the agent-readable budget. The seam is a
real one: fitting is science and serialisation is plumbing, and the plumbing carries caveats —
environment coupling, arbitrary code execution on load — that have nothing to do with the model.

`fit` re-exports both functions, so the nine call sites that already import them from there
continue to work; this module is where they now live.
"""

from __future__ import annotations

from pathlib import Path

from genomeos.surfaces.fit import FitConfig, SurfaceFit

#: Bumped whenever `SurfaceFit`'s fields change in a way that makes an older file unreadable.
FIT_FORMAT = 2

_FIT_FIELDS = (
    "variant_id",
    "config",
    "beta_design_applied",
    "lengthscale_prior_km",
    "beta_cohort_applied",
    "design_levels",
    "inducing_spacing_ratio",
    "correlation_range_km",
    "idata",
    "_model",
    "_centre",
    "_scale",
)


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
    """Reload a trusted-owner cache, reconstructing known format 1 without refitting.

    Format 1 retained the posterior and predictive graph but stored an obsolete scalar prior SD.
    Reconstruction keeps the expensive scientific work and discards only that scalar; unknown or
    incomplete payloads refuse rather than guessing. The input file is never rewritten.
    """
    import cloudpickle

    with Path(path).open("rb") as stream:
        payload = cloudpickle.load(stream)
    fit_format = payload.get("format") if isinstance(payload, dict) else None
    if (
        isinstance(fit_format, bool)
        or not isinstance(fit_format, int)
        or fit_format not in {1, FIT_FORMAT}
    ):
        raise ValueError(
            f"{path} is not a surface fit of a supported format (readable: 1, {FIT_FORMAT}); "
            "preserve it and investigate rather than guessing"
        )
    fit = payload.get("fit")
    if fit_format == FIT_FORMAT and not isinstance(fit, SurfaceFit):
        raise ValueError(f"{path}: format {FIT_FORMAT} payload does not contain a SurfaceFit")
    missing = [field for field in _FIT_FIELDS if not hasattr(fit, field)]
    if missing:
        raise ValueError(f"{path}: surface fit is missing required fields {missing}")
    if not isinstance(fit.config, FitConfig):
        raise ValueError(f"{path}: surface fit does not contain a valid FitConfig configuration")
    model = fit._model
    named_vars = getattr(model, "named_vars", {})
    missing_nodes = [name for name in ("x_pred", "freq_pred") if name not in named_vars]
    if missing_nodes:
        raise ValueError(f"{path}: retained model is missing predictive nodes {missing_nodes}")
    if fit_format == FIT_FORMAT and isinstance(fit, SurfaceFit):
        return fit
    return SurfaceFit(**{field: getattr(fit, field) for field in _FIT_FIELDS})

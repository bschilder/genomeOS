"""Immutable per-cell surface artifacts (design §5, §6).

§5 says artifacts are **immutable and keyed by** ``(variant_id, model_version, data_version)``:
a model change publishes new artifacts and never mutates a map someone has cited. Until now
nothing wrote them, which is why every figure cost a refit and why a fitted surface existed only
as a live Python object.

**A fit is not an artifact.** ``surfaces.fit.save_fit`` pickles the PyMC graph so predictions are
cheap to repeat, and its own docstring calls that a cache: pickle is coupled to the installed PyMC
and executes arbitrary code on load, so it can be neither archival nor shared. The artifact is
this parquet — per-cell posterior summaries, plain columns, readable by anything that reads
parquet in ten years, and the thing P4's read API is meant to serve (§5: "the read API reads
precomputed artifacts and aggregates them; it never computes science").

**The mask travels with the numbers.** Every row carries its ``support`` state and
``posterior_contraction``, because §4's answer to a persuasive-but-unfounded cline is that a
consumer must be able to tell measured from inferred without going back to the model. An artifact
of values alone would strip exactly the column that makes the surface honest.

Written with ``partition_cols=["variant_id"]`` so one variant can be published, superseded or
withdrawn without rewriting the others — which is what immutability requires in practice.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from genomeos.surfaces.fit import SurfaceFit
from genomeos.surfaces.mask import MaskConfig, classify_support

#: Bumped when the columns change. Written into the manifest so a reader can refuse an artifact it
#: does not understand rather than silently misreading one.
ARTIFACT_FORMAT = 1

#: The quantity a cell value carries. `allele_frequency` counts chromosomes; `carrier_frequency`
#: counts individuals and comes from copy-number-variable genes such as KIR, where there is no
#: diploid genotype to count alleles from (#133).
MEASUREMENTS: tuple[str, ...] = ("allele_frequency", "carrier_frequency")

#: §6's per-cell columns, in order.
ARTIFACT_COLUMNS: tuple[str, ...] = (
    "h3_index",
    "variant_id",
    "post_median",
    "post_mean",
    "post_sd",
    "q025",
    "q975",
    "q25",
    "q75",
    "support",
    "posterior_contraction",
    "dist_nearest_obs_km",
    "model_version",
    "data_version",
)

_EARTH_RADIUS_KM = 6371.0088


def _haversine_km(lat1, lon1, lat2, lon2):
    dlat, dlon = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = (
        np.sin(dlat / 2) ** 2
        + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))


@dataclass(frozen=True)
class ArtifactManifest:
    """What was published, keyed as §5 requires, so an artifact can be cited and superseded."""

    variant_id: str
    model_version: str
    data_version: str
    resolution: int
    n_cells: int
    correlation_range_km: float
    prior_frequency_sd: float
    likelihood: str
    lengthscale_sigma: float
    n_observations: int
    support_counts: dict[str, int]
    #: What the per-cell numbers mean. Required, with no default: an artifact holding carrier
    #: frequencies over individuals and one holding allele frequencies over chromosomes are
    #: indistinguishable by inspection, and a consumer that averages across both is wrong in a way
    #: nothing downstream can detect (#133). A publisher that cannot say which it holds is
    #: incomplete, not ready to publish.
    measurement: str
    artifact_format: int = ARTIFACT_FORMAT

    def __post_init__(self) -> None:
        if self.measurement not in MEASUREMENTS:
            raise ValueError(
                f"unknown measurement {self.measurement!r}; expected one of {MEASUREMENTS}"
            )

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2, sort_keys=True) + "\n"


def cell_table(
    fit: SurfaceFit,
    *,
    h3_index: list[str],
    lat: np.ndarray,
    lon: np.ndarray,
    observations: pd.DataFrame,
    variant_id: str,
    model_version: str,
    data_version: str,
    mask_config: MaskConfig | None = None,
) -> pd.DataFrame:
    """Per-cell posterior summaries with their support state, ready to publish.

    `observations` is needed for `dist_nearest_obs_km`, which is what the mask is computed from —
    the artifact carries the distance as well as the verdict so a consumer can apply a stricter
    threshold without refitting.
    """
    predicted = fit.predict(lat=lat, lon=lon)
    distance = np.min(
        _haversine_km(
            lat[:, None], lon[:, None],
            observations["lat"].to_numpy()[None, :], observations["lon"].to_numpy()[None, :],
        ),
        axis=1,
    )
    contraction = predicted["post_sd"].to_numpy() / fit.prior_frequency_sd
    support = classify_support(
        has_observation_centre=distance < 50.0,
        dist_nearest_obs_km=distance,
        posterior_contraction=contraction,
        correlation_range_km=fit.correlation_range_km,
        config=mask_config or MaskConfig(),
    )
    frame = pd.DataFrame(
        {
            "h3_index": h3_index,
            "variant_id": variant_id,
            "post_median": predicted["post_median"].to_numpy(),
            "post_mean": predicted["post_mean"].to_numpy(),
            "post_sd": predicted["post_sd"].to_numpy(),
            "q025": predicted["q025"].to_numpy(),
            "q975": predicted["q975"].to_numpy(),
            "q25": predicted["q25"].to_numpy(),
            "q75": predicted["q75"].to_numpy(),
            "support": support,
            "posterior_contraction": contraction,
            "dist_nearest_obs_km": distance,
            "model_version": model_version,
            "data_version": data_version,
        },
        columns=list(ARTIFACT_COLUMNS),
    )
    return frame


def publish(
    frame: pd.DataFrame, root: Path, *, manifest: ArtifactManifest, overwrite: bool = False
) -> Path:
    """Write one variant's artifact and its manifest under `root`.

    Refuses to overwrite by default. §5's immutability is the point: a model change publishes new
    artifacts under a new `model_version` rather than replacing a map someone has already cited,
    and a silent overwrite is precisely the failure that guarantee exists to prevent.
    """
    root = Path(root)
    stem = manifest.variant_id.replace(":", "__")
    directory = root / f"{stem}__{manifest.model_version}__{manifest.data_version}"
    if directory.exists() and not overwrite:
        raise FileExistsError(
            f"{directory} already exists. Artifacts are immutable (§5): publish under a new "
            "model_version rather than overwriting, or pass overwrite=True deliberately."
        )
    directory.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(directory / "cells.parquet", index=False)
    (directory / "manifest.json").write_text(manifest.to_json())
    return directory


def read(directory: Path) -> tuple[pd.DataFrame, dict]:
    """Read a published artifact and its manifest, refusing an unknown format."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("artifact_format") != ARTIFACT_FORMAT:
        raise ValueError(
            f"{directory} is artifact_format {manifest.get('artifact_format')!r}; "
            f"this build reads {ARTIFACT_FORMAT}"
        )
    return pd.read_parquet(directory / "cells.parquet"), manifest

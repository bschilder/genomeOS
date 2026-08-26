"""Publish per-cell surface artifacts from saved fits (design §5, §6).

    python scripts/publish_artifacts.py --fits data/store/fits --out data/store/artifacts \
        --hbs data/raw/map_hbs_surveys.csv --g6pd data/raw/map_g6pd_surveys.csv

Reads the fits `build_surfaces.py` saved and writes the immutable parquet each variant is meant to
be cited as. Separated from fitting on purpose: fitting is expensive and environment-coupled,
publishing is cheap and must be repeatable, and a figure or a national rollup should read the
artifact rather than re-running NUTS.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import h3
import numpy as np

from genomeos.observations.sources import map_g6pd, map_surveys
from genomeos.surfaces.artifacts import ArtifactManifest, cell_table, publish
from genomeos.surfaces.fit import load_fit
from genomeos.viz.basemap import h3_land_cells

LAYERS = {"hbs": map_surveys.load, "g6pd": map_g6pd.load}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fits", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--hbs", type=Path)
    ap.add_argument("--g6pd", type=Path)
    ap.add_argument("--h3-res", type=int, default=3)
    ap.add_argument("--model-version", default="v1")
    ap.add_argument("--data-version", default="map-2026-08")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    cells = h3_land_cells(args.h3_res)
    centres = np.array([h3.cell_to_latlng(c) for c in cells], dtype=float)
    lat, lon = centres[:, 0], centres[:, 1]
    print(f"H3 res {args.h3_res}: {len(cells)} land cells")

    for layer, loader in LAYERS.items():
        path = getattr(args, layer)
        if path is None:
            continue
        observations, _ = loader(path, args.data_version)
        variant_id = str(observations["variant_id"].iloc[0])
        stem = variant_id.replace(":", "__")
        fit_path = args.fits / f"{stem}.fit.pkl"
        if not fit_path.exists():
            print(f"  {variant_id}: no fit at {fit_path} — skipped")
            continue

        fit = load_fit(fit_path)
        frame = cell_table(
            fit,
            h3_index=cells,
            lat=lat,
            lon=lon,
            observations=observations,
            variant_id=variant_id,
            model_version=args.model_version,
            data_version=args.data_version,
        )
        counts = {s: int((frame["support"] == s).sum()) for s in sorted(set(frame["support"]))}
        manifest = ArtifactManifest(
            variant_id=variant_id,
            model_version=args.model_version,
            data_version=args.data_version,
            resolution=args.h3_res,
            n_cells=len(frame),
            correlation_range_km=round(float(fit.correlation_range_km), 1),
            prior_frequency_sd=round(float(fit.prior_frequency_sd), 5),
            likelihood=fit.config.likelihood,
            lengthscale_sigma=float(fit.config.lengthscale_sigma),
            n_observations=len(observations),
            support_counts=counts,
        )
        directory = publish(frame, args.out, manifest=manifest, overwrite=args.overwrite)
        size = (directory / "cells.parquet").stat().st_size / 1024
        print(f"  {variant_id}: {len(frame)} cells, {size:.0f} KB -> {directory}")
        print(f"      rho {fit.correlation_range_km:.0f} km   support {counts}")


if __name__ == "__main__":
    main()

# Local data and model store

What this project holds, where, and which parts are durable. Written because three separate pod
runs had their output destroyed, and because most of what the pipeline produces is deliberately
not in git.

## Layout

```
data/
  raw/                                  fetched sources — gitignored, re-fetchable by script
    map_hbs_surveys.csv                 scripts/fetch_map_hbs.py --layer hbs
    map_g6pd_surveys.csv                scripts/fetch_map_hbs.py --layer g6pd
    afnd_populations.tsv                scripts/fetch_afnd.py
    afnd_cache/                         one HTML page per AFND population, so a re-run is free
  store/
    fits/       <variant>.fit.pkl       trained models — a CACHE, not an artifact (see below)
    artifacts/  <variant>__<model>__<data>/
                  cells.parquet         the citable per-cell surface (§5, §6)
                  manifest.json         what was published, and under what assumptions
    INVENTORY.json                      checksums of everything above
reference/                              committed: Natural Earth countries, Piel 2013 estimates
tests/fixtures/                         committed: tiny, hand-checkable inputs
docs/figures/                           committed: review figures
```

## What is durable and what is not

| | in git | re-creatable | notes |
|---|---|---|---|
| `reference/`, `tests/fixtures/`, `docs/figures/` | **yes** | — | small, reviewable, diffable |
| `data/raw/` | no | **yes**, by script | sources are versioned upstream; a committed copy goes stale silently |
| `data/store/fits/*.pkl` | no | yes, by refitting | **~100 MB each** and environment-coupled |
| `data/store/artifacts/` | **yes** | yes, from a fit | 1.1 MB parquet per variant — the citable output |

## A fit is not an artifact

`surfaces.fit.save_fit` pickles the PyMC graph alongside the posterior so predictions are cheap to
repeat. That is a **cache**: pickle is coupled to the installed PyMC and pytensor, and it executes
arbitrary code on load, so it can be neither archival nor shared. It is also large — the HbS fit is
**121 MB** against a **1.1 MB** artifact, a 110x difference, because the posterior carries a draw
of `f`, `p` and `freq_pred` for every observation. The fits stay local; the artifacts are
committed.

The artifact is `store/artifacts/.../cells.parquet` — per-cell posterior summaries in plain
columns, readable by anything that reads parquet, and what §5 means when it says the read API
"reads precomputed artifacts and aggregates them; it never computes science".

Every row carries its `support` state, `posterior_contraction` and `dist_nearest_obs_km`. That is
not padding: §4's defence against a persuasive-but-unfounded cline is that a consumer can tell
measured from inferred without going back to the model, and the distance is carried so a stricter
threshold can be applied without refitting.

## Immutability is enforced, not just documented

Artifacts are keyed `(variant_id, model_version, data_version)` and `publish()` **refuses to
overwrite**. A refit publishes under a new `model_version` and coexists with what it supersedes,
so an older citation keeps resolving. A silent overwrite is exactly the failure that guarantee
exists to prevent.

## Rebuilding from nothing

```bash
python scripts/fetch_map_hbs.py --layer hbs  --out data/raw/map_hbs_surveys.csv
python scripts/fetch_map_hbs.py --layer g6pd --out data/raw/map_g6pd_surveys.csv
python scripts/fetch_afnd.py --out data/raw/afnd_populations.tsv --cache data/raw/afnd_cache

python scripts/build_surfaces.py --hbs data/raw/map_hbs_surveys.csv \
    --g6pd data/raw/map_g6pd_surveys.csv --out data/store/fits --draws 1200
python scripts/publish_artifacts.py --fits data/store/fits --out data/store/artifacts \
    --hbs data/raw/map_hbs_surveys.csv --g6pd data/raw/map_g6pd_surveys.csv
python scripts/store_inventory.py --root data --out data/store/INVENTORY.json
```

Fitting is ~20 min per variant on a laptop. **Do not run it on a pod expecting the output back**:
nothing copies `/workspace` off a pod, and that is how three runs' fits were lost. A pod can render
figures and push them to a branch (`runpod_fit.py --job surfaces` does), but a 6 MB fit has to be
produced where it will be kept.

## Known gap

The **artifacts and the inventory are committed**, so a published surface now survives this
laptop. The **fits (217 MB) and the AFND harvest (36 MB of cached pages) are not** — they are
re-creatable by script, and `INVENTORY.json` makes their loss *detectable* rather than
*survivable*. Remote storage — #33 specifies GCS — is the actual fix and is not built.

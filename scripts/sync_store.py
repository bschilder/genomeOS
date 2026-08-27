"""Sync the local data store to a private Hugging Face dataset (design §5).

    python scripts/sync_store.py push          # local -> hub
    python scripts/sync_store.py pull          # hub -> local
    python scripts/sync_store.py status

**Interim storage, deliberately.** §5 wants immutable published artifacts and #33 specifies GCS;
neither exists yet. This keeps the store in one addressable place until it does, and everything
here is plain files, so migrating to GCS later is a copy rather than a rewrite.

**Why a hub dataset rather than a Runpod network volume.** Volumes are datacenter-scoped, and the
account's existing ones show the cost of that: the same logical cache duplicated as
`biodocs-var-embed-us-ks-2`, `-ca-mtl-3`, `-us-ne-1` and three more. Pinning a pod to one
datacenter also fights `runpod_fit.py`'s capacity fallback across sixteen of them. A hub dataset is
reachable from a laptop, any pod and CI with one token, and is git-backed, so it is a versioned
store rather than a disk.

**What is synced, and what each part is for.**

- ``store/artifacts/`` — the citable per-cell surfaces. Small, durable, the thing #33 will publish.
- ``store/fits/`` — trained models. ~100 MB each and **a cache, not an artifact**: pickle is
  coupled to the installed PyMC and executes on load. Synced because refitting costs ~20 minutes,
  not because it is archival.
- ``raw/`` tables — fetched sources. The AFND population table is the one worth holding: it costs
  1,825 requests and about two hours to regenerate, against one request for everything else.

The 37 MB AFND page cache is **not** synced. It exists only to re-derive the population table
without re-scraping, and that table is itself committed — so shipping the pages would be paying
for the same thing twice.

**Licence.** AFND publishes none (#117). The dataset is **private**, so this is storage rather
than redistribution; that distinction is what makes it acceptable under the assumed-open decision,
and it is why `private=True` is not negotiable here.
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO_ID = "bschilder/genomeos-data"
REPO_TYPE = "dataset"

#: (local path, path in the repo). Order is deliberate: cheapest and most valuable first, so an
#: interrupted push still leaves the artifacts present.
SYNCED: tuple[tuple[str, str], ...] = (
    ("data/store/artifacts", "store/artifacts"),
    ("data/store/INVENTORY.json", "store/INVENTORY.json"),
    ("data/raw/afnd_populations.tsv", "raw/afnd_populations.tsv"),
    ("data/raw/afnd_frequencies.tsv", "raw/afnd_frequencies.tsv"),
    ("data/raw/map_hbs_surveys.csv", "raw/map_hbs_surveys.csv"),
    ("data/raw/map_g6pd_surveys.csv", "raw/map_g6pd_surveys.csv"),
    ("data/store/fits", "store/fits"),
    # The screening fits and their rendered surfaces. Added because a sweep is hours of sampling
    # that regenerates only by spending them again: the 17 AFND fits below cost about two hours
    # and lived in a session scratchpad until this line existed. `sweep.json` is small and carries
    # the fitted range, observation count and inducing-point budget per allele, so the summary
    # survives even if the pickles are pruned later.
    ("data/store/screen", "store/screen"),
    ("data/store/surfaces", "store/surfaces"),
)

#: Never synced. See the module docstring.
EXCLUDED = ("data/raw/afnd_cache",)


def _api():
    from huggingface_hub import HfApi

    return HfApi()


def push(dry_run: bool) -> None:
    api = _api()
    for local, remote in SYNCED:
        path = Path(local)
        if not path.exists():
            print(f"  skip (absent)   {local}")
            continue
        size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() \
            else path.stat().st_size
        print(f"  push {size / 1e6:8.1f} MB  {local} -> {remote}")
        if dry_run:
            continue
        if path.is_dir():
            api.upload_folder(
                folder_path=str(path), path_in_repo=remote,
                repo_id=REPO_ID, repo_type=REPO_TYPE,
            )
        else:
            api.upload_file(
                path_or_fileobj=str(path), path_in_repo=remote,
                repo_id=REPO_ID, repo_type=REPO_TYPE,
            )


def pull(dry_run: bool) -> None:
    from huggingface_hub import snapshot_download

    print(f"  pulling {REPO_ID} -> data/")
    if dry_run:
        return
    local = snapshot_download(repo_id=REPO_ID, repo_type=REPO_TYPE, local_dir="data/_hub")
    print(f"  downloaded to {local}")
    print("  move what you need into data/ — deliberately not overwriting in place, because a")
    print("  pull that silently replaces a fit you have not pushed is a bad default.")


def status() -> None:
    api = _api()
    try:
        files = api.list_repo_files(REPO_ID, repo_type=REPO_TYPE)
    except Exception as error:  # noqa: BLE001 - a missing repo is a status, not a crash
        print(f"  {REPO_ID}: unreachable ({type(error).__name__})")
        return
    info = api.repo_info(REPO_ID, repo_type=REPO_TYPE)
    print(f"  {REPO_ID}  private={info.private}  {len(files)} files")
    for name in sorted(files)[:20]:
        print(f"    {name}")
    if len(files) > 20:
        print(f"    ... and {len(files) - 20} more")
    print("\n  local, not synced:")
    for name in EXCLUDED:
        path = Path(name)
        if path.exists():
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            print(f"    {size / 1e6:8.1f} MB  {name}  (re-derivable; see the module docstring)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("push", "pull", "status"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    {"push": lambda: push(args.dry_run), "pull": lambda: pull(args.dry_run), "status": status}[
        args.action
    ]()


if __name__ == "__main__":
    main()

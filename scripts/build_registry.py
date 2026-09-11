"""Build the population registry to parquet (design §6, P0). Usage:

    python scripts/build_registry.py --hgdp data/raw/hgdp_populations.tsv \
        --release-version 0.1.0 --out data/registry-v1

HGDP input must follow the curated five-column contract documented in
`docs/hgdp-registry-input.md`.

`--afnd` takes an AFND population export in the format documented in
`genomeos.registry.sources.afnd`. AFND publishes no licence and no bulk download, so this
repository ships no fetcher for it and the file has to be obtained by agreement with AFND; the
adapter prints what it refused and why.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

import pandas as pd

from genomeos.registry.build import build_registry
from genomeos.registry.publication import publish_registry
from genomeos.registry.release_contract import (
    RegistryInput,
    _validate_release_version,
    identify_input,
)
from genomeos.registry.sources import afnd, hgdp


def _release_version(value: str) -> str:
    try:
        return _validate_release_version(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _snapshot(
    source: Path, snapshot_dir: Path, role: str
) -> tuple[Path, RegistryInput]:
    payload = source.read_bytes()
    snapshot = snapshot_dir / f"{role}.tsv"
    snapshot.write_bytes(payload)
    return snapshot, identify_input("source", role, payload)


def _implementation_input(role: str, path: Path) -> RegistryInput:
    return identify_input("implementation", role, path.read_bytes())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--hgdp",
        type=Path,
        required=True,
        help="curated HGDP TSV; see docs/hgdp-registry-input.md",
    )
    ap.add_argument("--afnd", type=Path)
    ap.add_argument("--release-version", type=_release_version, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    if os.path.lexists(os.fspath(args.out)):
        ap.error(f"registry publication destination already exists: {args.out}")

    inputs: list[RegistryInput] = [
        _implementation_input("scripts/build_registry.py", Path(__file__).resolve()),
        _implementation_input(
            "genomeos/registry/sources/hgdp.py", Path(hgdp.__file__).resolve()
        ),
    ]
    with tempfile.TemporaryDirectory(prefix="genomeos-registry-") as temporary:
        snapshot_dir = Path(temporary)
        hgdp_snapshot, hgdp_input = _snapshot(args.hgdp, snapshot_dir, "hgdp")
        inputs.append(hgdp_input)
        loaded: list[tuple[pd.DataFrame, pd.DataFrame]] = [
            hgdp.load(hgdp_snapshot, args.release_version)
        ]
        if args.afnd is not None:
            afnd_snapshot, afnd_input = _snapshot(args.afnd, snapshot_dir, "afnd")
            inputs.extend(
                [
                    afnd_input,
                    _implementation_input(
                        "genomeos/registry/sources/afnd.py", Path(afnd.__file__).resolve()
                    ),
                ]
            )
            afnd_populations, afnd_aliases, report = afnd.load(
                afnd_snapshot, args.release_version
            )
            print(report)
            loaded.append((afnd_populations, afnd_aliases))

        populations, aliases = build_registry(loaded)
        manifest = publish_registry(
            populations,
            aliases,
            inputs=tuple(inputs),
            release_version=args.release_version,
            out=args.out,
        )
    print(
        f"registry {manifest.registry_version}: "
        f"{len(populations)} populations, {len(aliases)} aliases"
    )


if __name__ == "__main__":
    main()

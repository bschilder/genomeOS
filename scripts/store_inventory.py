"""Inventory the local data and model store, with checksums (design §5).

    python scripts/store_inventory.py --root data --out data/store/INVENTORY.json

Answers one question: **what do we hold, and would we know if it went missing or changed?**

Most of what this project produces is gitignored — fetched sources are versioned upstream and
model fits are too large and too environment-coupled to commit — so the repository is not a record
of what exists. Three separate runs have already had their output destroyed with the pod that made
it. A checksummed inventory is the cheapest thing that turns "it is probably on the laptop" into a
statement that can be verified, and it is what a later move to remote storage would be checked
against.

Checksums are over content, not mtime: a file that silently changed is the failure worth catching,
and a timestamp cannot see it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

#: Directories that hold many small files whose individual hashes are noise. They are summarised
#: by count and total size rather than enumerated, so the inventory stays readable.
SUMMARISE_ONLY = ("afnd_cache",)

#: Anything larger than this is hashed in streamed chunks rather than read whole.
CHUNK = 1 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data"))
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    files, summaries, total = [], [], 0
    for path in sorted(args.root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.parts)
        total += path.stat().st_size
        bucket = next((name for name in SUMMARISE_ONLY if name in parts), None)
        if bucket is not None:
            continue
        files.append(
            {
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    for name in SUMMARISE_ONLY:
        for directory in sorted(args.root.rglob(name)):
            if not directory.is_dir():
                continue
            members = [p for p in directory.rglob("*") if p.is_file()]
            summaries.append(
                {
                    "path": str(directory),
                    "files": len(members),
                    "bytes": sum(p.stat().st_size for p in members),
                    "note": "summarised, not hashed per file",
                }
            )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "root": str(args.root),
        "total_bytes": total,
        "n_files_hashed": len(files),
        "files": files,
        "summarised_directories": summaries,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print(f"{len(files)} files hashed, {total / 1e6:.1f} MB total under {args.root}")
    for entry in files:
        print(f"  {entry['bytes'] / 1e3:9.1f} KB  {entry['sha256'][:12]}  {entry['path']}")
    for entry in summaries:
        print(f"  {entry['bytes'] / 1e6:9.1f} MB  {entry['files']:>5} files    {entry['path']}")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

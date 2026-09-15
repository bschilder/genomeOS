#!/usr/bin/env python3
"""Audit explicitly selected source storage without seeding it (design §10).

Use an existing SQLite database opened read-only. Output contains counts and
refusals, not private connection strings or synthetic scientific results.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from genomeos.evidence.query import audit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--offset", type=int, default=0)
    args = parser.parse_args()
    path = args.sqlite.resolve(strict=True)
    engine = create_engine(f"sqlite:///file:{quote(str(path), safe='/')}?mode=ro&uri=true")
    try:
        with Session(engine) as session:
            result = audit(session, offset=args.offset)
        # Exclusive create: an audit snapshot is never silently overwritten.
        with args.out.open("x") as stream:
            stream.write(result.model_dump_json(indent=2) + "\n")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

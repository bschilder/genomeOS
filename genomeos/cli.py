from __future__ import annotations

import argparse
from pathlib import Path

from .db import SessionLocal, init_db
from .ingest import ingest_associations, ingest_phenotype_manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="genomeos")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")

    manifest = sub.add_parser("ingest-panukb-manifest")
    manifest.add_argument("path", type=Path)
    manifest.add_argument("--version", required=True)
    manifest.add_argument("--source-uri")

    associations = sub.add_parser("index-panukb-associations")
    associations.add_argument("path", type=Path)
    associations.add_argument("--phenotype-id", type=int, required=True)
    associations.add_argument("--source-uri")
    associations.add_argument("--threshold", type=float, default=7.30103)
    associations.add_argument("--p-value-encoding", choices=("neg_log10", "ln", "raw"))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    init_db()
    if args.command == "init-db":
        print("database initialized")
        return
    with SessionLocal() as session:
        if args.command == "ingest-panukb-manifest":
            with args.path.open() as stream:
                count = ingest_phenotype_manifest(
                    session,
                    stream,
                    version=args.version,
                    source_uri=args.source_uri or str(args.path),
                )
        else:
            count = ingest_associations(
                session,
                args.path,
                phenotype_id=args.phenotype_id,
                source_uri=args.source_uri or str(args.path),
                threshold=args.threshold,
                p_value_encoding=args.p_value_encoding,
            )
    print(f"processed {count} records")


if __name__ == "__main__":
    main()

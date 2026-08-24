# genomeOS

Explore the genome; worldwide.

The first vertical slice provides a provenance-first API over Pan-UK Biobank
metadata and selectively indexed ancestry-stratified GWAS associations. Full
summary-statistics files remain in their public object storage and are queried
by genomic region through a Tabix boundary.

## Local development

```bash
python -m pip install -e '.[dev]'
genomeos init-db
uvicorn genomeos.api:app --reload
pytest
```

By default the service uses `sqlite:///./genomeos.db` for local development.
Production requires a PostgreSQL `DATABASE_URL`.

See [the Pan-UKB architecture](docs/panukb-architecture.md) and
[deployment guide](docs/deployment-gcp.md). GCP operations must use the
[repository-local gcloud wrapper](docs/repo-gcloud-auth.md).

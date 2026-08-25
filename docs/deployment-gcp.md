# GCP deployment

GenomeOS is intended to run on Cloud Run with Cloud SQL for PostgreSQL. The
deployment account must be supplied locally through `--account` or `GENOMEOS_GCP_ACCOUNT`;
do not deploy into a project
owned by another active account.

## Required setup

Authentication and configuration are repository-local. Follow
[`repo-gcloud-auth.md`](repo-gcloud-auth.md) and use:

```bash
python scripts/gcloud_repo.py auth login
python scripts/gcloud_repo.py init --project YOUR_GENOMEOS_PROJECT
```

Do not use plain `gcloud` for GenomeOS operations; it belongs to the global
configuration used by other repositories.

Enable Cloud Run, Cloud Build, Artifact Registry, Cloud SQL Admin, Secret
Manager, and Service Networking APIs. Create a PostgreSQL 17 Cloud SQL instance,
database, least-privilege application user, and store its password in Secret
Manager. Prefer the Cloud SQL connector over a public database address.

The application container accepts:

```text
DATABASE_URL
PANUKB_REGION_QUERY_ENABLED
PANUKB_REGION_MAX_ROWS
```

The active local GCP configuration must be verified before every deployment.
Infrastructure creation is intentionally not hidden inside the application
startup process.

`cloudbuild.yaml` builds the image in Artifact Registry. The Cloud Run template
at `deploy/cloudrun-service.yaml` contains explicit placeholders for the project,
region, Cloud SQL instance, service account, and image tag. Replace and review
those values before applying it; never deploy the template verbatim.

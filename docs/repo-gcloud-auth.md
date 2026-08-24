# Repository-local gcloud authentication

GenomeOS keeps its Google Cloud SDK state separate from the user-wide gcloud
configuration by setting:

```text
CLOUDSDK_CONFIG=.local/gcloud/genomeos
```

Use the wrapper for every GenomeOS authentication, configuration, deployment,
and Cloud Run/Cloud SQL inspection command:

```bash
python scripts/gcloud_repo.py auth login
python scripts/gcloud_repo.py init --account YOUR_GOOGLE_ACCOUNT --project YOUR_GENOMEOS_PROJECT
python scripts/gcloud_repo.py run auth list
python scripts/gcloud_repo.py run config list
```

No account identity or project is stored in Git. Pass `--account` and `--project` to `init`,
or set the local `GENOMEOS_GCP_ACCOUNT` and `GENOMEOS_GCP_PROJECT` environment variables.

Credentials and Cloud SDK state live under ignored `.local/gcloud/genomeos/`.
Never commit that directory, access tokens, application-default credentials, or
service-account keys. Plain `gcloud` continues to use the global configuration, so this wrapper
does not log out or modify accounts outside the repository-local SDK configuration.

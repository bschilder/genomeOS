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
python scripts/gcloud_repo.py init --project YOUR_GENOMEOS_PROJECT
python scripts/gcloud_repo.py run auth list
python scripts/gcloud_repo.py run config list
```

The default account is `dawei.lin100@gmail.com`. A project is deliberately not
guessed: pass `--project` to `init` or set `GENOMEOS_GCP_PROJECT`.

Credentials and Cloud SDK state live under ignored `.local/gcloud/genomeos/`.
Never commit that directory, access tokens, application-default credentials, or
service-account keys. Plain `gcloud` continues to use the global configuration,
so this wrapper does not log out or modify `business@zennai.pro`.

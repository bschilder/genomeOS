---
title: GitHub Pages deployment
description: How the static genomeOS site is validated and published at genome-os.org through GitHub Actions.
sidebar:
  order: 8
  label: Deployment
---

The site is statically rendered. Pull requests validate it; only a push to `main` uploads and
deploys a GitHub Pages artifact.

## Build boundary

Production uses:

```text
site = https://genome-os.org
base = /
```

Fallback verification uses:

```text
site = https://bschilder.github.io
base = /genomeOS
```

Internal paths pass through one base-aware helper. Broken links, missing assets, type errors,
content-contract failures, or accessibility violations stop deployment.

## Domain boundary

The repository Pages setting owns `genome-os.org`. Because Pages uses a custom Actions workflow,
GitHub ignores and does not require a repository `CNAME` file. DNS points the apex to GitHub's four
Pages IPv4 addresses and `www` directly to `bschilder.github.io`.

Domain ownership uses the permanent `_github-pages-challenge-bschilder` TXT record. GitHub can take
up to 24 hours after successful DNS configuration to provision HTTPS; enable **Enforce HTTPS** when
the repository setting becomes available.

See the [website design and deployment contract](https://github.com/bschilder/genomeOS/blob/main/docs/superpowers/specs/2026-09-05-docs-website-design.md).

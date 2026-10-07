---
title: Local development
description: Reproduce the Python and Astro environments and run the checks required before a genomeOS pull request.
sidebar:
  order: 7
---

The scientific package and website are separate runtimes in one repository.

## Python environment

Use Python 3.12 and the repository lock:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.lock
python -m pip install -e '.' --no-deps
```

Run the required gates:

```bash
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

## Atlas web objects

The `/app/` explorer loads binary GOSA objects (one shared H3 grid plus a render and a detail tier
per artifact) that are generated, not committed. `export_atlas_web.py` output is an intermediate;
the site build fails until `encode_atlas_web.py` has run. From the repository root, in the Python
environment above (or after `python -m pip install -c requirements.lock '.[read]'`, which pins
h3-py to the H3 core of the website's h3-js):

```bash
python scripts/encode_atlas_web.py
```

It writes `website/public/data/atlas/grids/` and `website/public/data/atlas/surfaces/` (both
git-ignored), verifies every object against the canonical JSON, and rewrites
`website/public/data/atlas/catalog.json` byte-for-byte as committed. Run it before `npm run dev`,
`npm test`, `npm run test:e2e` and `npm run test:performance`, and again whenever the exported
JSON changes; commit the catalog it writes. CI runs it and fails if the committed catalog differs.

## Website environment

Use Node 24 and the committed npm lock:

```bash
cd website
npm ci
npm run dev
```

Before a pull request:

```bash
npm run format:check
npm run check
npm test
npm run build
npm run build:fallback
npm run test:e2e
```

`npm run test:e2e` matches CI: one Playwright worker against a server on `127.0.0.1:4322`. Two
environment variables change that locally. `PLAYWRIGHT_WORKERS` (a positive integer, default 1)
sets the worker count. Pass `--fully-parallel` with it, or each file stays on one worker.
`PLAYWRIGHT_PORT` (1 to 65535, default 4322) moves the test server that `npm run serve:test` starts
for both `test:e2e` and `test:performance`, so two checkouts can run their suites at once, for
example `PLAYWRIGHT_PORT=4352 PLAYWRIGHT_WORKERS=4 npm run test:e2e -- --fully-parallel`. CI sets
neither variable; it splits the suite across four runners with `--shard` instead.

The custom-domain build assumes `/`; the fallback build assumes `/genomeOS`. Both must work so a
domain transition cannot hide broken internal paths.

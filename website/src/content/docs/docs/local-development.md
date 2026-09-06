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

The custom-domain build assumes `/`; the fallback build assumes `/genomeOS`. Both must work so a
domain transition cannot hide broken internal paths.

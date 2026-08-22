# Genome OS Atlas — Implementation Plan 1: Data Foundation (P0 + P1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Context

`bschilder/genomeOS` is an empty repo with an approved design spec at `docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md` (PR #5). The spec covers six sub-projects (P0–P5); per the writing-plans scope check, each needs its own plan that produces working, testable software on its own. **This is Plan 1 of 3**, and it builds the data foundation:

- **P0** — the population geolocation registry. The spec's central finding is that the binding constraint on this whole project is *coordinates, not variants*: gnomAD v4 has 800k people and no usable geography, HGDP has coordinates and 929 people. Nothing can be mapped until every population label has a coordinate, a provenance, and an uncertainty radius.
- **P1** — the observations store. Georeferenced allele counts with the §7.1 ascertainment metadata, which is required for the `β_design`/`β_cohort` correction and cannot be retrofitted without re-ingesting everything.

**Outcome:** a queryable, schema-validated observations table where every row has coordinates and a known ascertainment design — the sole input to Plan 2's surface fitting. No maps yet, by design.

**Roadmap for the rest:** Plan 2 = P2 + P3 (surface inference, burden engine, golden tests 1–3, ending at HbS parity). Plan 3 = P4 + P5 (read API, Map mode UI). The GH Project below spans all three so the board is complete from day one.

**Architecture:** A Python package (`src/genomeos/`) of pure, offline, unit-testable modules, mirroring the `services/compute/engines.py` pattern in `standardmodelbio/hg-horizon-web` — science modules carry no HTTP or I/O dependency so they test directly. Source adapters normalise each dataset into one schema; the schema is the contract, enforced by pandera and frozen into `contract/` so drift shows up in diffs.

**Tech Stack:** Python 3.12 · `uv` · pandera ≥0.23 · pyarrow · duckdb · h3-py ≥4 · pytest. Parquet on GCS. (Plan 3 adds Next.js 16 / React 19 / TypeScript 5 / vitest / deck.gl / MapLibre, matching hg-horizon-web.)

## Global Constraints

- **Schema is the contract.** Every ingested row validates against the pandera schema before it is written. Validation failures are hard errors, never dropped rows — a population label with no coordinate must fail the build loudly (spec §12).
- **Ascertainment fields are mandatory** on every observation: `sampling_design`, `disease_ascertainment_excluded`, `cohort_id` (spec §6, §7.1). No source adapter may emit a row without them.
- **`uncertainty_radius_km` has no default.** A coordinate without a stated radius is invalid (spec §6). Sampling location ≠ ancestral location; `location_type` is required.
- **Determinism.** `SEED = 42` in any module with a stochastic path, matching `services/compute/engines.py`.
- Coordinates are WGS84 decimal degrees. Variant IDs are `chr-pos-ref-alt` on **GRCh38**. Dates are years BP (modern = 0).
- Reuse the house patterns from `standardmodelbio/hg-horizon-web`: pure-engine/thin-wrapper split (`services/compute/engines.py` vs `app.py`), a frozen data contract checked in CI (`contract/bundle.schema.json` + `scripts/check-contract.mjs`), and HF-hosted data pulled by script rather than committed (`scripts/fetch-data.mjs`).
- CI must stay green: `uv run pytest`, `uv run ruff check`, `uv run pyright`.
- Module docstrings cite the spec section they implement (`design §7.1`), as in `engines.py`.

**Deliberate refinement of the spec:** §6 specifies `source_labels` as a nested `array<struct<source,label>>`. This plan normalises it into a second table, `population_aliases(population_id, source, label)`. Nested columns are awkward to validate and to join; a long table makes alias collisions detectable (Task 4) and the join testable. Spec §6 should be amended to match once this lands.

---

## File Structure

```
pyproject.toml                          # uv project, py3.12, deps + ruff/pyright config
AGENTS.md                               # conventions; CLAUDE.md is just "@AGENTS.md"
.github/workflows/ci.yml                # pytest + ruff + pyright
contract/
  populations.schema.json               # frozen, emitted by scripts/freeze_contract.py
  population_aliases.schema.json
  observations.schema.json
src/genomeos/
  registry/
    schema.py                           # POPULATIONS_SCHEMA, ALIASES_SCHEMA  (P0)
    build.py                            # build_registry() + collision detection
    sources/hgdp.py                     # reference adapter; one module per source
  observations/
    schema.py                           # OBSERVATIONS_SCHEMA incl. ascertainment (P1)
    ingest.py                           # normalise + validate + partitioned parquet write
    sources/gnomad_hgdp_1kg.py
    sources/map_surveys.py              # population_random — identifies beta_design
  geo/h3util.py                         # lat/lon -> H3, resolution ladder
tests/
  fixtures/                             # tiny checked-in source fixtures
  test_registry_schema.py  test_registry_build.py  test_hgdp_source.py
  test_observations_schema.py  test_gnomad_source.py  test_map_surveys.py
  test_h3util.py  test_ingest.py  test_contract_frozen.py
scripts/
  build_registry.py  build_observations.py  freeze_contract.py
```

**Deliberately not in Plan 1: the curated variant set** (spec §15 lists it under P1). It is board issue 19, and it needs clinical-genetics review to decide which ClinVar P/LP variants have defensible penetrance — a role with no owner on the roster yet. It gates P2 rather than P1 (you cannot fit surfaces without a variant list), so it belongs at the start of Plan 2 alongside the INLA runtime decision. Plan 1's deliverable is the *store*, which is variant-agnostic.

---

## Task 1: Repo scaffold, CI, conventions

**Files:**
- Create: `pyproject.toml`, `AGENTS.md`, `CLAUDE.md`, `.github/workflows/ci.yml`
- Create: `src/genomeos/__init__.py`, `tests/test_smoke.py`

**Interfaces:**
- Produces: `genomeos.__version__` (str). Every later task imports from `genomeos.*`.

- [ ] **Step 1: Write the failing test** — `tests/test_smoke.py`

```python
def test_package_imports_and_reports_version():
    import genomeos

    assert isinstance(genomeos.__version__, str)
    assert genomeos.__version__
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos'`

- [ ] **Step 3: Create `pyproject.toml`**

```toml
[project]
name = "genomeos"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pandera[pandas]>=0.23,<1",
    "pandas>=2.2",
    "pyarrow>=17",
    "duckdb>=1.1",
    "h3>=4.1",
]

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6", "pyright>=1.1.380"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/genomeos"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 110
target-version = "py312"

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
```

- [ ] **Step 4: Create `src/genomeos/__init__.py`**

```python
"""Genome OS Atlas — data foundation (design P0/P1).

Pure, offline, unit-testable modules. Nothing here performs HTTP I/O or holds
serving-path state: per design §5, all science lives in offline functions that are
deterministic given (config, data_version, seed).
"""

__version__ = "0.1.0"
```

- [ ] **Step 5: Run the test — expect PASS**

Run: `uv run pytest tests/test_smoke.py -v`
Expected: PASS

- [ ] **Step 6: Create `AGENTS.md`** (and `CLAUDE.md` containing only `@AGENTS.md`, matching hg-horizon-web)

```markdown
# Genome OS Atlas — conventions

Read `docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md` before writing code.
Module docstrings cite the spec section they implement, e.g. `design §7.1`.

## Invariants (violating these is a bug, not a style choice)
- **Observations and surfaces are never conflated.** Observations are measured; surfaces are
  inferred. Separate tables, separate layers, separate provenance. (§4, §5)
- **No inference on the serving path.** All fitting is offline and batch. (§5)
- **Schema violations are hard errors.** Never silently drop a row. (§12)
- **`uncertainty_radius_km` and the ascertainment fields have no defaults.** (§6, §7.1)
- Science modules carry no HTTP dependency, so they unit-test directly
  (pattern: `services/compute/engines.py` in hg-horizon-web).

## Commands
`uv sync` · `uv run pytest` · `uv run ruff check` · `uv run pyright`
```

- [ ] **Step 7: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: uv sync --all-groups
      - run: uv run ruff check
      - run: uv run pyright
      - run: uv run pytest -v
```

- [ ] **Step 8: Verify the full suite and lint pass**

Run: `uv sync --all-groups && uv run ruff check && uv run pytest -v`
Expected: ruff clean, 1 test passing

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml AGENTS.md CLAUDE.md .github/workflows/ci.yml src tests
git commit -m "chore: scaffold genomeos package, CI, conventions"
```

---

## Task 2: Registry schema (P0)

**Files:**
- Create: `src/genomeos/registry/__init__.py`, `src/genomeos/registry/schema.py`
- Test: `tests/test_registry_schema.py`

**Interfaces:**
- Produces: `POPULATIONS_SCHEMA: pandera.pandas.DataFrameSchema`, `ALIASES_SCHEMA: pandera.pandas.DataFrameSchema`, `LOCATION_TYPES: tuple[str, ...]`. Consumed by Tasks 3, 4 and by `scripts/build_registry.py`.

- [ ] **Step 1: Write the failing test** — `tests/test_registry_schema.py`

```python
import pandas as pd
import pandera.errors
import pytest

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


def _valid_row(**overrides) -> pd.DataFrame:
    row = {
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "uncertainty_radius_km": 50.0,
        "location_type": "ancestral",
        "provenance": "10.1126/science.1078311",
        "biocultural_notice": None,
        "registry_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_valid_population_row_passes():
    POPULATIONS_SCHEMA.validate(_valid_row())


@pytest.mark.parametrize(
    "overrides",
    [
        {"lat": 91.0},                      # out of range
        {"lon": -181.0},                    # out of range
        {"uncertainty_radius_km": 0.0},      # must be > 0
        {"uncertainty_radius_km": None},     # no default permitted
        {"location_type": "guessed"},        # not in enum
        {"provenance": ""},                  # must be non-empty
        {"population_id": "HGDP Yoruba"},    # must be slug-cased
    ],
)
def test_invalid_population_rows_are_rejected(overrides):
    with pytest.raises(pandera.errors.SchemaError):
        POPULATIONS_SCHEMA.validate(_valid_row(**overrides))


def test_duplicate_population_id_is_rejected():
    dup = pd.concat([_valid_row(), _valid_row()], ignore_index=True)
    with pytest.raises(pandera.errors.SchemaError):
        POPULATIONS_SCHEMA.validate(dup)


def test_aliases_reject_duplicate_source_label_pair():
    dup = pd.DataFrame(
        [
            {"population_id": "hgdp-yoruba", "source": "hgdp", "label": "Yoruba"},
            {"population_id": "onekg-yri", "source": "hgdp", "label": "Yoruba"},
        ]
    )
    with pytest.raises(pandera.errors.SchemaError):
        ALIASES_SCHEMA.validate(dup)
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_registry_schema.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos.registry'`

- [ ] **Step 3: Implement `src/genomeos/registry/schema.py`**

```python
"""Population geolocation registry schema (design §6, sub-project P0).

The registry is the join table that gives every population label a coordinate. Per design §2's
central finding, coordinates — not variants — are the binding constraint on the whole atlas, so
this schema is deliberately strict: `uncertainty_radius_km` has no default, `provenance` cannot
be empty, and `location_type` must state whether the coordinate is where the sample was *taken*
or where the population is *from* (design §4 — 1KG labels such as GBR/ASW are diaspora sampling
sites, not ancestral origins).

Aliases live in a separate long table rather than the nested `array<struct>` of §6: a long table
makes collisions detectable (see registry.build) and the join testable.
"""

from __future__ import annotations

import pandera.pandas as pa

LOCATION_TYPES: tuple[str, ...] = ("sampling", "ancestral", "inferred")

_SLUG = r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$"

POPULATIONS_SCHEMA = pa.DataFrameSchema(
    {
        "population_id": pa.Column(
            str, pa.Check.str_matches(_SLUG), nullable=False, unique=True
        ),
        "lat": pa.Column(float, pa.Check.in_range(-90.0, 90.0), nullable=False),
        "lon": pa.Column(float, pa.Check.in_range(-180.0, 180.0), nullable=False),
        # No default: a coordinate without a stated extent is not usable (design §7 weights
        # each observation as a disc of this radius, not as a point).
        "uncertainty_radius_km": pa.Column(float, pa.Check.gt(0.0), nullable=False),
        "location_type": pa.Column(str, pa.Check.isin(LOCATION_TYPES), nullable=False),
        "provenance": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        # CARE-aligned notice for entries derived from indigenous-population panels (§13).
        "biocultural_notice": pa.Column(str, nullable=True, required=True),
        "registry_version": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    strict=True,
    coerce=True,
    name="populations",
)

ALIASES_SCHEMA = pa.DataFrameSchema(
    {
        "population_id": pa.Column(str, pa.Check.str_matches(_SLUG), nullable=False),
        "source": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "label": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    strict=True,
    coerce=True,
    unique=["source", "label"],
    name="population_aliases",
)
```

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_registry_schema.py -v`
Expected: all PASS (10 cases)

- [ ] **Step 5: Commit**

```bash
git add src/genomeos/registry tests/test_registry_schema.py
git commit -m "feat(P0): population registry schema with strict coordinate contract"
```

---

## Task 3: HGDP registry source adapter (the reference adapter)

**Files:**
- Create: `src/genomeos/registry/sources/__init__.py`, `src/genomeos/registry/sources/hgdp.py`
- Create fixture: `tests/fixtures/hgdp_populations.tsv` (6 rows, hand-written)
- Test: `tests/test_hgdp_source.py`

**Interfaces:**
- Produces: `load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]` returning `(populations, aliases)`, each already conforming to the Task 2 schemas. **Every source adapter in P0 has this exact signature** — Task 4 depends on it.

- [ ] **Step 1: Create the fixture** — `tests/fixtures/hgdp_populations.tsv`

```
population	latitude	longitude	region
Yoruba	7.38	3.90	Africa
Biaka	4.00	17.00	Africa
Han	32.27	114.02	East Asia
Sardinian	40.10	9.00	Europe
Karitiana	-10.00	-63.00	America
Papuan	-4.00	143.00	Oceania
```

- [ ] **Step 2: Write the failing test** — `tests/test_hgdp_source.py`

```python
from pathlib import Path

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA
from genomeos.registry.sources import hgdp

FIXTURE = Path(__file__).parent / "fixtures" / "hgdp_populations.tsv"


def test_load_conforms_to_schemas():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)


def test_load_slugs_ids_and_preserves_original_label_as_alias():
    populations, aliases = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert set(populations["population_id"]) >= {"hgdp-yoruba", "hgdp-sardinian"}
    yoruba = aliases[aliases["population_id"] == "hgdp-yoruba"].iloc[0]
    assert yoruba["source"] == "hgdp"
    assert yoruba["label"] == "Yoruba"


def test_hgdp_coordinates_are_ancestral_with_a_stated_radius():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert (populations["location_type"] == "ancestral").all()
    assert (populations["uncertainty_radius_km"] > 0).all()


def test_hgdp_entries_carry_a_biocultural_notice():
    populations, _ = hgdp.load(FIXTURE, registry_version="0.1.0")
    assert populations["biocultural_notice"].notna().all()
```

- [ ] **Step 3: Run it — expect FAIL**

Run: `uv run pytest tests/test_hgdp_source.py -v`
Expected: FAIL, `ImportError: cannot import name 'hgdp'`

- [ ] **Step 4: Implement `src/genomeos/registry/sources/hgdp.py`**

```python
"""HGDP registry adapter (design §6, P0) — the reference implementation of the adapter contract.

Every registry source module exposes the same `load(path, registry_version)` signature and
returns `(populations, aliases)` conforming to `registry.schema`. HGDP coordinates are the
Cavalli-Sforza panel's *ancestral* sampling localities, so `location_type = "ancestral"`.

HGDP is an indigenous-population panel, so every entry carries a CARE-aligned biocultural
notice per design §13.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SOURCE = "hgdp"

# HGDP localities are villages/regions, not points. 50 km is the panel-wide default extent; a
# per-population refinement is future work tracked as its own issue.
DEFAULT_RADIUS_KM = 50.0

PROVENANCE = "10.1126/science.1078311"  # Cann et al. 2002, HGDP-CEPH panel
BIOCULTURAL_NOTICE = (
    "Indigenous-population panel. Reuse governed by the CARE Principles; see "
    "https://www.gida-global.org/careprinciples"
)


def slugify(label: str) -> str:
    """`"Yoruba"` -> `"hgdp-yoruba"`; matches the `_SLUG` pattern in registry.schema."""
    cleaned = re.sub(r"[^a-z0-9]+", "-", label.strip().lower()).strip("-")
    return f"{SOURCE}-{cleaned}"


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path, sep="\t")
    missing = {"population", "latitude", "longitude"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    ids = raw["population"].map(slugify)

    populations = pd.DataFrame(
        {
            "population_id": ids,
            "lat": raw["latitude"].astype(float),
            "lon": raw["longitude"].astype(float),
            "uncertainty_radius_km": DEFAULT_RADIUS_KM,
            "location_type": "ancestral",
            "provenance": PROVENANCE,
            "biocultural_notice": BIOCULTURAL_NOTICE,
            "registry_version": registry_version,
        }
    )
    aliases = pd.DataFrame(
        {"population_id": ids, "source": SOURCE, "label": raw["population"].astype(str)}
    )
    return populations, aliases
```

- [ ] **Step 5: Run the tests — expect PASS**

Run: `uv run pytest tests/test_hgdp_source.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/genomeos/registry/sources tests/test_hgdp_source.py tests/fixtures/hgdp_populations.tsv
git commit -m "feat(P0): HGDP registry adapter establishing the source-adapter contract"
```

---

## Task 4: Registry build with alias-collision detection

**Files:**
- Create: `src/genomeos/registry/build.py`
- Create: `scripts/build_registry.py`
- Test: `tests/test_registry_build.py`

**Interfaces:**
- Consumes: any module exposing `load(path, registry_version) -> (populations, aliases)` (Task 3's contract).
- Produces: `build_registry(loaded: list[tuple[pd.DataFrame, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame]` and `class AliasCollisionError(ValueError)`. Consumed by Task 6's join.

**Why this task exists:** the same label appearing in two sources mapped to two different `population_id`s is the single most likely silent corruption in P0 — it splits one population's observations across two map points. It must be a hard error (Global Constraints).

- [ ] **Step 1: Write the failing test** — `tests/test_registry_build.py`

```python
import pandas as pd
import pytest

from genomeos.registry.build import AliasCollisionError, build_registry
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


def _source(pop_id: str, source: str, label: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    populations = pd.DataFrame(
        [
            {
                "population_id": pop_id,
                "lat": 7.38,
                "lon": 3.9,
                "uncertainty_radius_km": 50.0,
                "location_type": "ancestral",
                "provenance": "doi:test",
                "biocultural_notice": None,
                "registry_version": "0.1.0",
            }
        ]
    )
    aliases = pd.DataFrame([{"population_id": pop_id, "source": source, "label": label}])
    return populations, aliases


def test_build_concatenates_and_validates():
    populations, aliases = build_registry(
        [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("onekg-yri", "onekg", "YRI")]
    )
    POPULATIONS_SCHEMA.validate(populations)
    ALIASES_SCHEMA.validate(aliases)
    assert len(populations) == 2


def test_same_source_label_mapped_to_two_ids_is_a_hard_error():
    with pytest.raises(AliasCollisionError, match="Yoruba"):
        build_registry(
            [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("onekg-yri", "hgdp", "Yoruba")]
        )


def test_duplicate_population_id_across_sources_is_a_hard_error():
    with pytest.raises(Exception):
        build_registry(
            [_source("hgdp-yoruba", "hgdp", "Yoruba"), _source("hgdp-yoruba", "afnd", "Yoruba*")]
        )
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_registry_build.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos.registry.build'`

- [ ] **Step 3: Implement `src/genomeos/registry/build.py`**

```python
"""Assemble the population registry from source adapters (design §6, P0).

A `(source, label)` pair resolving to two different `population_id`s would silently split one
population's observations across two map points — the most damaging failure mode available in
P0 — so it raises rather than warns (design §12: schema violations are hard errors).
"""

from __future__ import annotations

import pandas as pd

from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA


class AliasCollisionError(ValueError):
    """One (source, label) pair maps to more than one population_id."""


def build_registry(
    loaded: list[tuple[pd.DataFrame, pd.DataFrame]],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not loaded:
        raise ValueError("build_registry requires at least one source")

    populations = pd.concat([p for p, _ in loaded], ignore_index=True)
    aliases = pd.concat([a for _, a in loaded], ignore_index=True)

    collisions = (
        aliases.groupby(["source", "label"])["population_id"].nunique().loc[lambda s: s > 1]
    )
    if not collisions.empty:
        detail = ", ".join(f"{src}/{lbl}" for src, lbl in collisions.index)
        raise AliasCollisionError(f"alias collisions (one label -> several population_id): {detail}")

    orphans = set(aliases["population_id"]) - set(populations["population_id"])
    if orphans:
        raise ValueError(f"aliases reference unknown population_id: {sorted(orphans)}")

    return POPULATIONS_SCHEMA.validate(populations), ALIASES_SCHEMA.validate(aliases)
```

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_registry_build.py -v`
Expected: 3 PASS

- [ ] **Step 5: Add the build entrypoint** — `scripts/build_registry.py`

```python
"""Build the population registry to parquet. Usage:
    uv run python scripts/build_registry.py --hgdp data/raw/hgdp_populations.tsv --out data/registry
"""

from __future__ import annotations

import argparse
from pathlib import Path

from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hgdp", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    populations, aliases = build_registry([hgdp.load(args.hgdp, VERSION)])
    args.out.mkdir(parents=True, exist_ok=True)
    populations.to_parquet(args.out / "populations.parquet", index=False)
    aliases.to_parquet(args.out / "population_aliases.parquet", index=False)
    print(f"registry v{VERSION}: {len(populations)} populations, {len(aliases)} aliases")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run it end to end against the fixture**

Run: `uv run python scripts/build_registry.py --hgdp tests/fixtures/hgdp_populations.tsv --out /tmp/reg`
Expected: `registry v0.1.0: 6 populations, 6 aliases`

- [ ] **Step 7: Commit**

```bash
git add src/genomeos/registry/build.py scripts/build_registry.py tests/test_registry_build.py
git commit -m "feat(P0): registry build with alias-collision and orphan detection"
```

---

## Task 5: Observations schema with ascertainment fields (P1)

**Files:**
- Create: `src/genomeos/observations/__init__.py`, `src/genomeos/observations/schema.py`
- Test: `tests/test_observations_schema.py`

**Interfaces:**
- Produces: `OBSERVATIONS_SCHEMA: DataFrameSchema`, `SAMPLING_DESIGNS: tuple[str, ...]`, `VARIANT_ID_PATTERN: str`. Consumed by Tasks 6, 8 and `scripts/build_observations.py`.

- [ ] **Step 1: Write the failing test** — `tests/test_observations_schema.py`

```python
import pandas as pd
import pandera.errors
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA, SAMPLING_DESIGNS


def _row(**overrides) -> pd.DataFrame:
    row = {
        "variant_id": "chr11-5227002-T-A",
        "rsid": "rs334",
        "population_id": "hgdp-yoruba",
        "lat": 7.38,
        "lon": 3.9,
        "radius_km": 50.0,
        "ac": 12,
        "an": 200,
        "source": "map_surveys",
        "assay": "genotype",
        "date_lower": 0,
        "date_upper": 0,
        "sampling_design": "population_random",
        "disease_ascertainment_excluded": False,
        "cohort_id": "map-hbs-ng-001",
        "ingest_version": "0.1.0",
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_valid_observation_passes():
    OBSERVATIONS_SCHEMA.validate(_row())


def test_every_sampling_design_in_the_enum_is_accepted():
    for design in SAMPLING_DESIGNS:
        OBSERVATIONS_SCHEMA.validate(_row(sampling_design=design))


@pytest.mark.parametrize(
    "overrides",
    [
        {"ac": -1},                                # counts are non-negative
        {"an": 0},                                 # an must be > 0
        {"ac": 300, "an": 200},                    # ac may not exceed an
        {"sampling_design": None},                 # mandatory, no default (§7.1)
        {"sampling_design": "unknown"},            # not in enum
        {"disease_ascertainment_excluded": None},  # mandatory
        {"cohort_id": ""},                         # mandatory, non-empty
        {"variant_id": "11:5227002T>A"},           # must be chr-pos-ref-alt on GRCh38
        {"date_lower": -5},                        # years BP, non-negative
    ],
)
def test_invalid_observations_are_rejected(overrides):
    with pytest.raises(pandera.errors.SchemaError):
        OBSERVATIONS_SCHEMA.validate(_row(**overrides))


def test_zero_count_observation_is_valid_and_not_dropped():
    """AC=0 with AN=200 is weak evidence, not evidence of absence (design §7.1b)."""
    OBSERVATIONS_SCHEMA.validate(_row(ac=0))
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_observations_schema.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos.observations'`

- [ ] **Step 3: Implement `src/genomeos/observations/schema.py`**

```python
"""Georeferenced allele-count observations (design §6, §7.1, sub-project P1).

This is the "what was measured" layer of design §5 — never to be conflated with fitted
surfaces. Two properties are load-bearing:

1. **Counts, not frequencies.** We store `ac` and `an` rather than `ac/an` because a zero count
   out of 200 alleles is weak evidence, not evidence of absence; the binomial likelihood in §7
   depends on `an` being present (§7.1b).
2. **Ascertainment is mandatory.** `sampling_design`, `disease_ascertainment_excluded` and
   `cohort_id` are what make the `β_design` / `β_cohort` correction in §7.1 estimable at all.
   None of the four ascertainment biases can be modelled without them, and they cannot be
   retrofitted without re-ingesting every source — hence no defaults and no nullability.
"""

from __future__ import annotations

import pandera.pandas as pa

SAMPLING_DESIGNS: tuple[str, ...] = (
    "population_random",
    "healthy_reference",
    "clinical_case",
    "clinical_control",
    "newborn_screening",
    "carrier_screening",
    "convenience",
)

# chr-pos-ref-alt on GRCh38 (Global Constraints).
VARIANT_ID_PATTERN = r"^chr(?:[1-9]|1[0-9]|2[0-2]|X|Y|M)-\d+-[ACGT]+-[ACGT]+$"

OBSERVATIONS_SCHEMA = pa.DataFrameSchema(
    {
        "variant_id": pa.Column(str, pa.Check.str_matches(VARIANT_ID_PATTERN), nullable=False),
        "rsid": pa.Column(str, nullable=True, required=True),
        "population_id": pa.Column(str, nullable=False),
        "lat": pa.Column(float, pa.Check.in_range(-90.0, 90.0), nullable=False),
        "lon": pa.Column(float, pa.Check.in_range(-180.0, 180.0), nullable=False),
        "radius_km": pa.Column(float, pa.Check.gt(0.0), nullable=False),
        "ac": pa.Column(int, pa.Check.ge(0), nullable=False),
        "an": pa.Column(int, pa.Check.gt(0), nullable=False),
        "source": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "assay": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        # Years before present; modern = 0, ancient from AADR (§7 time axis).
        "date_lower": pa.Column(int, pa.Check.ge(0), nullable=False),
        "date_upper": pa.Column(int, pa.Check.ge(0), nullable=False),
        "sampling_design": pa.Column(str, pa.Check.isin(SAMPLING_DESIGNS), nullable=False),
        "disease_ascertainment_excluded": pa.Column(bool, nullable=False),
        "cohort_id": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
        "ingest_version": pa.Column(str, pa.Check.str_length(min_value=1), nullable=False),
    },
    checks=[
        pa.Check(lambda df: df["ac"] <= df["an"], name="ac_le_an", error="ac must not exceed an"),
        pa.Check(
            lambda df: df["date_lower"] <= df["date_upper"],
            name="date_lower_le_upper",
            error="date_lower must not exceed date_upper",
        ),
    ],
    strict=True,
    coerce=True,
    name="observations",
)
```

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_observations_schema.py -v`
Expected: all PASS (12 cases)

- [ ] **Step 5: Commit**

```bash
git add src/genomeos/observations tests/test_observations_schema.py
git commit -m "feat(P1): observations schema with mandatory ascertainment fields (§7.1)"
```

---

## Task 6: gnomAD HGDP+1KG observation adapter + registry join

**Files:**
- Create: `src/genomeos/observations/sources/__init__.py`, `src/genomeos/observations/sources/gnomad_hgdp_1kg.py`
- Create fixture: `tests/fixtures/gnomad_hgdp_1kg_freqs.tsv`
- Test: `tests/test_gnomad_source.py`

**Interfaces:**
- Consumes: `POPULATIONS_SCHEMA`/`ALIASES_SCHEMA` frames from Task 4; `OBSERVATIONS_SCHEMA` from Task 5.
- Produces: `load(path: Path, populations: pd.DataFrame, aliases: pd.DataFrame, ingest_version: str) -> pd.DataFrame`, and `class UnmappedPopulationError(ValueError)`. **Every observation adapter in P1 has this signature.**

**Why the join lives here:** the adapter is the only place that knows a source's population labels, so it is the only place that can fail loudly when a label has no coordinate (Global Constraints, spec §12).

- [ ] **Step 1: Create the fixture** — `tests/fixtures/gnomad_hgdp_1kg_freqs.tsv`

```
variant_id	rsid	pop_label	AC	AN
chr11-5227002-T-A	rs334	Yoruba	24	226
chr11-5227002-T-A	rs334	Sardinian	0	194
chr7-117559590-ATCT-A	rs113993960	Sardinian	3	198
chr7-117559590-ATCT-A	rs113993960	Han	0	206
```

- [ ] **Step 2: Write the failing test** — `tests/test_gnomad_source.py`

```python
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.registry.build import build_registry
from genomeos.registry.sources import hgdp

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registry():
    return build_registry([hgdp.load(FIXTURES / "hgdp_populations.tsv", "0.1.0")])


def test_load_conforms_to_schema(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) == 4


def test_coordinates_and_radius_come_from_the_registry(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    yoruba = obs[obs["population_id"] == "hgdp-yoruba"].iloc[0]
    assert yoruba["lat"] == pytest.approx(7.38)
    assert yoruba["radius_km"] == pytest.approx(50.0)


def test_gnomad_is_marked_disease_depleted_healthy_reference(registry):
    """gnomAD excludes severe pediatric disease cases and their first-degree relatives (§7.1a)."""
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    assert (obs["sampling_design"] == "healthy_reference").all()
    assert obs["disease_ascertainment_excluded"].all()


def test_zero_count_rows_are_retained(registry):
    populations, aliases = registry
    obs = gnomad.load(FIXTURES / "gnomad_hgdp_1kg_freqs.tsv", populations, aliases, "0.1.0")
    assert (obs["ac"] == 0).sum() == 2


def test_unmapped_population_label_is_a_hard_error(tmp_path, registry):
    populations, aliases = registry
    bad = tmp_path / "bad.tsv"
    bad.write_text(
        "variant_id\trsid\tpop_label\tAC\tAN\nchr11-5227002-T-A\trs334\tAtlantis\t1\t100\n"
    )
    with pytest.raises(gnomad.UnmappedPopulationError, match="Atlantis"):
        gnomad.load(bad, populations, aliases, "0.1.0")
```

- [ ] **Step 3: Run it — expect FAIL**

Run: `uv run pytest tests/test_gnomad_source.py -v`
Expected: FAIL, `ImportError: cannot import name 'gnomad_hgdp_1kg'`

- [ ] **Step 4: Implement `src/genomeos/observations/sources/gnomad_hgdp_1kg.py`**

```python
"""gnomAD HGDP+1KG harmonized callset adapter (design §6, P1).

The harmonized HGDP+1kGP callset (4,094 genomes, 80 populations, CC0) is the only open resource
that is simultaneously whole-genome and georeferenceable per-population — design §15's
recommended starting point.

Ascertainment (§7.1a): gnomAD excludes individuals with severe pediatric disease *and their
first-degree relatives* by policy, so every row is `healthy_reference` with
`disease_ascertainment_excluded = True`. That flag is what lets `β_design` be estimated later;
it is not a caveat in a docstring, it is data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "gnomad_hgdp_1kg"
ALIAS_SOURCES = ("hgdp", "onekg")
COHORT_ID = "gnomad-v4-hgdp-1kg"


class UnmappedPopulationError(ValueError):
    """A source population label has no entry in the registry, so it has no coordinate."""


def load(
    path: Path,
    populations: pd.DataFrame,
    aliases: pd.DataFrame,
    ingest_version: str,
) -> pd.DataFrame:
    raw = pd.read_csv(path, sep="\t")

    lookup = aliases[aliases["source"].isin(ALIAS_SOURCES)].set_index("label")["population_id"]
    unmapped = sorted(set(raw["pop_label"]) - set(lookup.index))
    if unmapped:
        raise UnmappedPopulationError(
            f"{path}: population labels absent from the registry (add them to P0 first): {unmapped}"
        )

    coords = populations.set_index("population_id")[["lat", "lon", "uncertainty_radius_km"]]
    pop_ids = raw["pop_label"].map(lookup)

    obs = pd.DataFrame(
        {
            "variant_id": raw["variant_id"].astype(str),
            "rsid": raw["rsid"].astype(str),
            "population_id": pop_ids.to_numpy(),
            "lat": coords.loc[pop_ids, "lat"].to_numpy(),
            "lon": coords.loc[pop_ids, "lon"].to_numpy(),
            "radius_km": coords.loc[pop_ids, "uncertainty_radius_km"].to_numpy(),
            "ac": raw["AC"].astype(int),
            "an": raw["AN"].astype(int),
            "source": SOURCE,
            "assay": "genome",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "healthy_reference",
            "disease_ascertainment_excluded": True,
            "cohort_id": COHORT_ID,
            "ingest_version": ingest_version,
        }
    )
    return OBSERVATIONS_SCHEMA.validate(obs)
```

- [ ] **Step 5: Run the tests — expect PASS**

Run: `uv run pytest tests/test_gnomad_source.py -v`
Expected: 5 PASS

- [ ] **Step 6: Commit**

```bash
git add src/genomeos/observations/sources tests/test_gnomad_source.py tests/fixtures/gnomad_hgdp_1kg_freqs.tsv
git commit -m "feat(P1): gnomAD HGDP+1KG adapter with registry join and hard unmapped-label error"
```

---

## Task 7: MAP survey adapter (the `population_random` anchor)

**Files:**
- Create: `src/genomeos/observations/sources/map_surveys.py`
- Create fixture: `tests/fixtures/map_hbs_surveys.tsv`
- Test: `tests/test_map_surveys.py`

**Interfaces:**
- Produces: `load(path: Path, ingest_version: str) -> pd.DataFrame` — note this adapter takes **no registry**, because MAP surveys carry their own point coordinates rather than population labels. Consumed by Plan 2's golden test 1.

**Why this task is in Plan 1 and not Plan 2:** these are the only `population_random` observations in the corpus. `β_design` is identified by contrast between design types (spec §7.1), so without this source the ascertainment correction is unidentifiable and Plan 2 cannot start. It is also the input to HbS parity.

- [ ] **Step 1: Create the fixture** — `tests/fixtures/map_hbs_surveys.tsv`

```
site_name	latitude	longitude	AC	AN	year	citation
Ibadan	7.38	3.90	61	400	1979	doi:10.1038/ncomms1104
Kumasi	6.69	-1.62	48	360	1981	doi:10.1038/ncomms1104
Cagliari	39.22	9.12	2	280	1985	doi:10.1038/ncomms1104
```

- [ ] **Step 2: Write the failing test** — `tests/test_map_surveys.py`

```python
from pathlib import Path

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.observations.sources import map_surveys

FIXTURE = Path(__file__).parent / "fixtures" / "map_hbs_surveys.tsv"


def test_load_conforms_to_schema():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    OBSERVATIONS_SCHEMA.validate(obs)
    assert len(obs) == 3


def test_surveys_are_population_random_and_not_disease_depleted():
    """MAP surveys are population screening surveys — the reference design for β_design (§7.1a)."""
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert (obs["sampling_design"] == "population_random").all()
    assert not obs["disease_ascertainment_excluded"].any()


def test_each_survey_site_is_its_own_cohort():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert obs["cohort_id"].nunique() == 3


def test_all_rows_are_the_hbs_variant():
    obs = map_surveys.load(FIXTURE, "0.1.0")
    assert (obs["variant_id"] == map_surveys.HBS_VARIANT_ID).all()
    assert (obs["rsid"] == "rs334").all()
```

- [ ] **Step 3: Run it — expect FAIL**

Run: `uv run pytest tests/test_map_surveys.py -v`
Expected: FAIL, `ImportError: cannot import name 'map_surveys'`

- [ ] **Step 4: Implement `src/genomeos/observations/sources/map_surveys.py`**

```python
"""Malaria Atlas Project HbS survey adapter (design §6, §8, P1).

The open georeferenced HbS survey database behind Piel et al. 2010/2013. Two reasons it matters
disproportionately for its size:

1. It is the input to **golden test 1** (HbS parity, §8) — the only end-to-end validation of the
   pipeline against independently published national estimates.
2. These are population screening surveys, so they are the corpus's reference
   `population_random` design. `β_design` (§7.1a) is identified by contrast *between* designs, so
   without a well-ascertained anchor the correction is unidentifiable.

Survey sites carry their own point coordinates, so this adapter needs no registry join. Each
site is its own `cohort_id`: survey-level effects are exactly what `β_cohort` absorbs (§7.1d).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA

SOURCE = "map_surveys"
HBS_VARIANT_ID = "chr11-5227002-T-A"  # rs334, HBB Glu6Val, GRCh38
SURVEY_RADIUS_KM = 25.0  # survey catchment; MAP models these as point-referenced with a locality


def _cohort_id(site_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(site_name).strip().lower()).strip("-")
    return f"map-hbs-{slug}"


def load(path: Path, ingest_version: str) -> pd.DataFrame:
    raw = pd.read_csv(path, sep="\t")
    missing = {"site_name", "latitude", "longitude", "AC", "AN"} - set(raw.columns)
    if missing:
        raise ValueError(f"{path}: missing required columns {sorted(missing)}")

    obs = pd.DataFrame(
        {
            "variant_id": HBS_VARIANT_ID,
            "rsid": "rs334",
            "population_id": raw["site_name"].map(_cohort_id),
            "lat": raw["latitude"].astype(float),
            "lon": raw["longitude"].astype(float),
            "radius_km": SURVEY_RADIUS_KM,
            "ac": raw["AC"].astype(int),
            "an": raw["AN"].astype(int),
            "source": SOURCE,
            "assay": "genotype",
            "date_lower": 0,
            "date_upper": 0,
            "sampling_design": "population_random",
            "disease_ascertainment_excluded": False,
            "cohort_id": raw["site_name"].map(_cohort_id),
            "ingest_version": ingest_version,
        }
    )
    return OBSERVATIONS_SCHEMA.validate(obs)
```

- [ ] **Step 5: Run the tests — expect PASS**

Run: `uv run pytest tests/test_map_surveys.py -v`
Expected: 4 PASS

- [ ] **Step 6: Commit**

```bash
git add src/genomeos/observations/sources/map_surveys.py tests/test_map_surveys.py tests/fixtures/map_hbs_surveys.tsv
git commit -m "feat(P1): MAP HbS survey adapter — the population_random anchor for beta_design"
```

---

## Task 8: H3 indexing and the resolution ladder

**Files:**
- Create: `src/genomeos/geo/__init__.py`, `src/genomeos/geo/h3util.py`
- Test: `tests/test_h3util.py`

**Interfaces:**
- Produces: `RESOLUTION_LADDER: tuple[int, ...] = (4, 5, 6)`, `GLOBAL_RESOLUTION: int = 4`, `cell_for(lat: float, lon: float, res: int) -> str`, `parent_of(cell: str, res: int) -> str`, `cells_within_km(lat: float, lon: float, radius_km: float, res: int) -> list[str]`. Consumed by Plan 2's surface fitting and Plan 3's viewport queries.

- [ ] **Step 1: Write the failing test** — `tests/test_h3util.py`

```python
import h3
import pytest

from genomeos.geo.h3util import (
    GLOBAL_RESOLUTION,
    RESOLUTION_LADDER,
    cell_for,
    cells_within_km,
    parent_of,
)


def test_ladder_is_ascending_and_starts_at_the_global_resolution():
    assert RESOLUTION_LADDER == tuple(sorted(RESOLUTION_LADDER))
    assert RESOLUTION_LADDER[0] == GLOBAL_RESOLUTION
    assert RESOLUTION_LADDER[-1] == 6, "res 6 is the finest v1 emits (design §6)"


def test_cell_for_is_deterministic_and_round_trips_to_the_same_cell():
    a = cell_for(7.38, 3.9, 4)
    assert a == cell_for(7.38, 3.9, 4)
    assert h3.get_resolution(a) == 4


def test_parent_of_walks_up_the_ladder():
    fine = cell_for(7.38, 3.9, 6)
    assert parent_of(fine, 4) == cell_for(7.38, 3.9, 4)


def test_parent_of_rejects_a_finer_target_resolution():
    coarse = cell_for(7.38, 3.9, 4)
    with pytest.raises(ValueError):
        parent_of(coarse, 6)


def test_cells_within_km_covers_the_centre_and_grows_with_radius():
    near = cells_within_km(7.38, 3.9, 30.0, 4)
    far = cells_within_km(7.38, 3.9, 300.0, 4)
    assert cell_for(7.38, 3.9, 4) in near
    assert len(far) > len(near)


def test_cells_within_km_rejects_a_non_positive_radius():
    with pytest.raises(ValueError):
        cells_within_km(7.38, 3.9, 0.0, 4)
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_h3util.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos.geo'`

- [ ] **Step 3: Implement `src/genomeos/geo/h3util.py`**

```python
"""H3 spatial indexing and the resolution ladder (design §6, P1).

H3 rather than a raster format because design §6 needs region aggregation to become a
`WHERE h3_parent IN (...)` predicate pushdown in DuckDB, and because deck.gl's `H3HexagonLayer`
consumes the indexes directly — one geometry stack instead of two.

Ladder: res 4 (~1,770 km²/cell, 288,122 cells globally) is the global default. Res 5 (~253 km²)
and res 6 (~36 km²) are populated only where observation density supports promotion (§7). Res 6
is the finest v1 emits — finer exceeds what any open georeferenced panel justifies (§4).
"""

from __future__ import annotations

import h3

GLOBAL_RESOLUTION: int = 4
RESOLUTION_LADDER: tuple[int, ...] = (4, 5, 6)

_EARTH_RADIUS_KM = 6371.0088


def _check_resolution(res: int) -> None:
    if res not in RESOLUTION_LADDER:
        raise ValueError(f"resolution {res} is not in the ladder {RESOLUTION_LADDER}")


def cell_for(lat: float, lon: float, res: int) -> str:
    _check_resolution(res)
    return h3.latlng_to_cell(lat, lon, res)


def parent_of(cell: str, res: int) -> str:
    _check_resolution(res)
    if res > h3.get_resolution(cell):
        raise ValueError(f"cannot take a res-{res} parent of a res-{h3.get_resolution(cell)} cell")
    return h3.cell_to_parent(cell, res)


def cells_within_km(lat: float, lon: float, radius_km: float, res: int) -> list[str]:
    """Every res-`res` cell whose centre lies within `radius_km` of (lat, lon).

    Used to place an observation as a disc of its `radius_km` rather than as a point (§7), and to
    compute `eff_n_in_range` for the data-support mask (§7).
    """
    _check_resolution(res)
    if radius_km <= 0:
        raise ValueError("radius_km must be > 0")

    origin = h3.latlng_to_cell(lat, lon, res)
    edge_km = h3.average_hexagon_edge_length(res, unit="km")
    rings = max(1, int(radius_km / edge_km) + 1)
    return [
        cell
        for cell in h3.grid_disk(origin, rings)
        if _haversine_km(lat, lon, *h3.cell_to_latlng(cell)) <= radius_km
    ]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(a))
```

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_h3util.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add src/genomeos/geo tests/test_h3util.py
git commit -m "feat(P1): H3 indexing helpers and the res 4-6 resolution ladder"
```

---

## Task 9: Observation ingest, partitioned parquet write, and frozen contract

**Files:**
- Create: `src/genomeos/observations/ingest.py`
- Create: `scripts/build_observations.py`, `scripts/freeze_contract.py`
- Create: `contract/observations.schema.json`, `contract/populations.schema.json`
- Test: `tests/test_ingest.py`, `tests/test_contract_frozen.py`

**Interfaces:**
- Consumes: adapter outputs from Tasks 6 and 7; `OBSERVATIONS_SCHEMA` from Task 5.
- Produces: `write_observations(obs: pd.DataFrame, out_dir: Path) -> Path` (partitioned by `chrom`), `read_observations(out_dir: Path, variant_id: str | None = None) -> pd.DataFrame`.

**Contract rationale:** mirrors `contract/bundle.schema.json` + `scripts/check-contract.mjs` in hg-horizon-web. The frozen JSON is checked in, so any schema change shows up as a reviewable diff rather than a silent break for downstream consumers (Plan 3's TypeScript client).

- [ ] **Step 1: Write the failing tests** — `tests/test_ingest.py`

```python
from pathlib import Path

import pandas as pd
import pytest

from genomeos.observations.ingest import read_observations, write_observations
from genomeos.observations.sources import map_surveys

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def obs() -> pd.DataFrame:
    return map_surveys.load(FIXTURES / "map_hbs_surveys.tsv", "0.1.0")


def test_write_partitions_by_chromosome(tmp_path, obs):
    out = write_observations(obs, tmp_path)
    assert (out / "chrom=chr11").is_dir()


def test_round_trip_preserves_row_count_and_counts(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path)
    assert len(back) == len(obs)
    assert back["ac"].sum() == obs["ac"].sum()


def test_read_can_filter_to_one_variant(tmp_path, obs):
    write_observations(obs, tmp_path)
    back = read_observations(tmp_path, variant_id=map_surveys.HBS_VARIANT_ID)
    assert len(back) == 3
    assert read_observations(tmp_path, variant_id="chr1-1-A-T").empty


def test_write_rejects_a_frame_that_violates_the_schema(tmp_path, obs):
    broken = obs.copy()
    broken.loc[0, "sampling_design"] = "unknown"
    with pytest.raises(Exception):
        write_observations(broken, tmp_path)
```

- [ ] **Step 2: Run them — expect FAIL**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'genomeos.observations.ingest'`

- [ ] **Step 3: Implement `src/genomeos/observations/ingest.py`**

```python
"""Validate and persist observations as chromosome-partitioned parquet (design §6, P1).

Partitioned by `chrom` because every downstream read is either per-variant (Plan 3's API) or
per-chromosome (Plan 2's batch fits); partitioning turns both into a directory prune instead of
a scan. Validation happens on write, so an invalid frame can never reach storage (§12).
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from genomeos.observations.schema import OBSERVATIONS_SCHEMA


def _chrom(variant_id: pd.Series) -> pd.Series:
    return variant_id.str.split("-").str[0]


def write_observations(obs: pd.DataFrame, out_dir: Path) -> Path:
    validated = OBSERVATIONS_SCHEMA.validate(obs).copy()
    validated["chrom"] = _chrom(validated["variant_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    validated.to_parquet(out_dir, partition_cols=["chrom"], index=False)
    return out_dir


def read_observations(out_dir: Path, variant_id: str | None = None) -> pd.DataFrame:
    glob = str(Path(out_dir) / "**" / "*.parquet")
    sql = f"SELECT * EXCLUDE (chrom) FROM read_parquet('{glob}', hive_partitioning = true)"
    params: list[object] = []
    if variant_id is not None:
        # Prune the partition as well as filter, so a per-variant read never scans other chroms.
        sql += " WHERE chrom = ? AND variant_id = ?"
        params = [variant_id.split("-")[0], variant_id]
    return duckdb.sql(sql, params=params).df() if params else duckdb.sql(sql).df()
```

- [ ] **Step 4: Run the tests — expect PASS**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: 4 PASS

- [ ] **Step 5: Write the contract-freeze script and its test**

`scripts/freeze_contract.py`:

```python
"""Freeze the pandera schemas to JSON in contract/ so schema drift appears in diffs.

Mirrors contract/bundle.schema.json + scripts/check-contract.mjs in hg-horizon-web. Plan 3's
TypeScript client validates against these files.

    uv run python scripts/freeze_contract.py            # write
    uv run python scripts/freeze_contract.py --check     # CI: fail if stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from genomeos.observations.schema import OBSERVATIONS_SCHEMA
from genomeos.registry.schema import ALIASES_SCHEMA, POPULATIONS_SCHEMA

CONTRACT_DIR = Path(__file__).resolve().parents[1] / "contract"
SCHEMAS = {
    "populations.schema.json": POPULATIONS_SCHEMA,
    "population_aliases.schema.json": ALIASES_SCHEMA,
    "observations.schema.json": OBSERVATIONS_SCHEMA,
}


def _serialise(schema) -> str:
    return json.dumps(json.loads(schema.to_json()), indent=2, sort_keys=True) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    CONTRACT_DIR.mkdir(exist_ok=True)
    stale = []
    for name, schema in SCHEMAS.items():
        path, text = CONTRACT_DIR / name, _serialise(schema)
        if args.check:
            if not path.exists() or path.read_text() != text:
                stale.append(name)
        else:
            path.write_text(text)

    if stale:
        print(f"contract is stale: {stale}\nrun: uv run python scripts/freeze_contract.py", file=sys.stderr)
        return 1
    print("contract up to date" if args.check else f"wrote {len(SCHEMAS)} schemas")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/test_contract_frozen.py`:

```python
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_frozen_contract_matches_the_live_schemas():
    result = subprocess.run(
        [sys.executable, "scripts/freeze_contract.py", "--check"],
        cwd=REPO, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 6: Generate the contract, then verify the check passes**

Run: `uv run python scripts/freeze_contract.py && uv run pytest tests/test_contract_frozen.py -v`
Expected: `wrote 3 schemas`, then PASS

- [ ] **Step 7: Add the contract check to CI**

In `.github/workflows/ci.yml`, insert before the `uv run pytest -v` step:

```yaml
      - run: uv run python scripts/freeze_contract.py --check
```

- [ ] **Step 8: Write the ingest entrypoint** — `scripts/build_observations.py`

```python
"""Build the observations store from all P1 sources.

    uv run python scripts/build_observations.py \
        --registry data/registry --gnomad data/raw/gnomad_hgdp_1kg_freqs.tsv \
        --map-surveys data/raw/map_hbs_surveys.tsv --out data/observations
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genomeos.observations.ingest import write_observations
from genomeos.observations.sources import gnomad_hgdp_1kg as gnomad
from genomeos.observations.sources import map_surveys

VERSION = "0.1.0"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", type=Path, required=True)
    ap.add_argument("--gnomad", type=Path, required=True)
    ap.add_argument("--map-surveys", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    populations = pd.read_parquet(args.registry / "populations.parquet")
    aliases = pd.read_parquet(args.registry / "population_aliases.parquet")

    frames = [
        gnomad.load(args.gnomad, populations, aliases, VERSION),
        map_surveys.load(args.map_surveys, VERSION),
    ]
    obs = pd.concat(frames, ignore_index=True)
    write_observations(obs, args.out)

    by_design = obs["sampling_design"].value_counts().to_dict()
    print(f"observations v{VERSION}: {len(obs)} rows, {obs['variant_id'].nunique()} variants")
    print(f"  by sampling_design: {by_design}")
```

- [ ] **Step 9: Run the whole pipeline end to end on fixtures**

```bash
uv run python scripts/build_registry.py --hgdp tests/fixtures/hgdp_populations.tsv --out /tmp/reg
uv run python scripts/build_observations.py --registry /tmp/reg \
  --gnomad tests/fixtures/gnomad_hgdp_1kg_freqs.tsv \
  --map-surveys tests/fixtures/map_hbs_surveys.tsv --out /tmp/obs
```

Expected: `registry v0.1.0: 6 populations, 6 aliases`, then `observations v0.1.0: 7 rows, 2 variants` with `{'healthy_reference': 4, 'population_random': 3}`.

**This two-design breakdown is the acceptance signal for Plan 1** — it is what makes `β_design` identifiable in Plan 2.

- [ ] **Step 10: Full suite + lint**

Run: `uv run ruff check && uv run pyright && uv run pytest -v`
Expected: clean, ~50 tests passing (parametrised cases count individually)

- [ ] **Step 11: Commit**

```bash
git add src/genomeos/observations/ingest.py scripts/ contract/ tests/test_ingest.py tests/test_contract_frozen.py .github/workflows/ci.yml
git commit -m "feat(P1): partitioned observation store, frozen data contract, CI drift check"
```

---

## Verification (end to end)

1. **Unit + lint:** `uv sync --all-groups && uv run ruff check && uv run pyright && uv run pytest -v` — all green.
2. **Contract not drifted:** `uv run python scripts/freeze_contract.py --check` → `contract up to date`.
3. **Pipeline on fixtures:** run the two commands in Task 9 Step 9 and confirm the printed row counts and the two-design breakdown.
4. **Round-trip query:** confirm a per-variant read prunes to one chromosome:
   ```bash
   uv run python -c "
   from pathlib import Path
   from genomeos.observations.ingest import read_observations
   df = read_observations(Path('/tmp/obs'), 'chr11-5227002-T-A')
   print(df[['population_id','ac','an','sampling_design']].to_string(index=False))
   "
   ```
   Expected: 5 rows (2 gnomAD `healthy_reference` + 3 MAP `population_random`) for rs334.
5. **Failure paths are loud, not silent** — each is already covered by a test, but confirm by hand that an unknown population label raises `UnmappedPopulationError` and an out-of-enum `sampling_design` raises on write.

**Definition of done for Plan 1:** every observation row carries coordinates, a radius, and a known ascertainment design; at least two distinct `sampling_design` values are present so `β_design` is identifiable; the contract is frozen and CI-checked. Plan 2 (P2 + P3, ending at HbS parity) can then begin.

---

## Flagged for Plan 2 (decide before starting, not now)

**The spec specifies INLA-SPDE, and R-INLA is R-only.** Three options, in my order of preference: (a) containerise R + R-INLA and call it from Python via `subprocess` with a parquet hand-off — keeps the spec's stated method and its defensibility, adds an R toolchain; (b) `sdmTMB`/TMB — still R; (c) reimplement in Python (PyMC or GPyTorch variational GP) — single language, but abandons the "same lineage as the model-based geostatistics literature" argument in §7 that makes the method defensible to reviewers. This is a real decision with a cost either way and it belongs at the top of Plan 2.

---

## GitHub Project

### Verified constraints

- **Decision: the repo stays on `bschilder`, and "types" are labels.** Labels work normally on personal repos and group/filter identically in Projects v2. The only thing genuinely unavailable is GitHub's *native issue-type field*, which is organisation-only — `/orgs/bschilder/issue-types` returns 404 and `type` is `null` on issue #3.
- **Sub-issues do work** on personal repos (`sub_issues_summary` is present on the issue payload), so the requested hierarchy is achievable via `POST /repos/{owner}/{repo}/issues/{n}/sub_issues`.
- **The built-in "Item closed" project workflow cannot distinguish Done from Not Planned** — it sets a single Status value. Splitting on `state_reason` (`completed` vs `not_planned`) requires the small Action in Task G3.

### Task G0: Publish the plan, tag collaborators, merge open PRs

Do this **before** creating labels/issues, so the board links to merged, citable documents.

- [ ] Commit this plan to the repo at `docs/superpowers/plans/2026-08-22-atlas-data-foundation.md` on branch `docs/atlas-plan-1`, and open a PR.
- [ ] Comment on **PR #5** (spec) and the plan PR tagging all three collaborators with write access — verified as `@dwgoblue`, `@JirachiWishmaster`, `@ctbio123` — pointing each at the sections that need their eyes:
  - `@dwgoblue` — spec §7.1 (ascertainment correction), §9 (burden expressions), golden tests 2 and 3
  - `@JirachiWishmaster` — spec §10 (backend: DuckDB reads / BigQuery batch), §11 (deck.gl layers), §6 (H3 parquet vs raster)
  - `@ctbio123` — spec §13 (governance), §14.1 (redistribution position), §14.3–4 (PGG.SNV and 23andMe outreach)
- [ ] Also tag them on [Discussion #4](https://github.com/bschilder/genomeOS/discussions/4) (prior art) and the use-case comments on Discussions #1 and #2, so review is distributed rather than all landing on one person.
- [ ] Merge **PR #5** (spec) then the plan PR, both with `--squash`, and delete the branches.
- [ ] Verify `main` contains `docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md` and `docs/superpowers/plans/2026-08-22-atlas-data-foundation.md`.

### Milestones

Four milestones, mapped to **plan/release boundaries rather than to P0–P5**. That's deliberate: sub-project is already encoded twice (the `P*:` label and the Project's *Sub-project* field), so mirroring it a third time in milestones adds no information. Release boundaries instead give each milestone a progress bar that answers a question someone actually asks:

| Milestone | Covers | Answers |
|---|---|---|
| **M1 — Data foundation** | P0 + P1 (issues 1–20) | Does every observation have a coordinate and a known ascertainment design? |
| **M2 — HbS parity** | P2 + P3 (issues 21–35) | Can we reproduce Piel et al.'s national estimates? *This is spec §8's definition of done.* |
| **M3 — Map mode** | P4 + P5 (issues 36–51) | Can someone open a browser and use it? |
| **M4 — Public launch** | issues 52–56 | Is it safe and legible to open to outside contributors? |

Milestones carry due dates and a native % complete that Projects v2 fields don't, and they show on the issue itself — so they complement the board rather than duplicating it. Assign the milestone to **both** parent and sub-issues, since milestone progress counts issues, not hierarchy.

```bash
gh api repos/bschilder/genomeOS/milestones -f title="M1 — Data foundation" \
  -f description="P0 + P1. Every observation carries coordinates and a known ascertainment design; contract frozen and CI-checked."
# repeat for M2-M4; capture each returned `number` for the issue-creation step
```

### Task G1: Labels as types, and skill labels

Create with `gh label create`. Type labels (mutually exclusive by convention):

`type:data` · `type:science` · `type:infra` · `type:ui` · `type:docs` · `type:governance` · `type:outreach`

Sub-project labels: `P0:registry` · `P1:observations` · `P2:surfaces` · `P3:burden` · `P4:backend` · `P5:map-ui`

Skill labels, so a contributor can filter to what they can actually do:

`skill:spatial-stats` · `skill:popgen` · `skill:clinical-genetics` · `skill:data-engineering` · `skill:frontend` · `skill:geospatial` · `skill:governance` · `skill:partnerships`

### Task G2: Issue hierarchy (6 parents, ~34 sub-issues)

Each **P-issue** is a parent; its children are the sub-issues. Suggested owner and skill in brackets.

**P0 — Population geolocation registry** `type:data` `skill:popgen`
1. Registry schema + strict coordinate contract `[@bschilder, spatial-stats/popgen]` ← Plan 1 Task 2
2. HGDP adapter (reference adapter) `[@bschilder]` ← Task 3
3. Build + alias-collision detection `[@bschilder]` ← Task 4
4. 1KG adapter — sampling-vs-ancestral flags for GBR/ASW-type labels `[@dwgoblue]`
5. AFND adapter (1,324 populations) `[@dwgoblue]`
6. SGDP + GAsP adapters `[@dwgoblue]`
7. AADR adapter (per-individual coords + dates) `[@dwgoblue]`
8. Per-population radius refinement, replacing the 50 km default `[needs: geospatial]`
9. CARE / biocultural notices for indigenous-panel entries `[@ctbio123, governance]`
10. Publish the registry as a standalone citable dataset `[@bschilder, docs]`

**P1 — Observations store** `type:data` `skill:data-engineering`
11. Observations schema incl. ascertainment fields `[@bschilder]` ← Task 5
12. gnomAD HGDP+1KG adapter + registry join `[@bschilder]` ← Task 6
13. MAP HbS/G6PD survey adapter `[@bschilder]` ← Task 7
14. H3 indexing + resolution ladder `[@JirachiWishmaster, geospatial]` ← Task 8
15. Partitioned parquet store + frozen contract `[@JirachiWishmaster]` ← Task 9
16. MCPS, IndiGen, GenomeIndia adapters `[@dwgoblue]`
17. Non-Western disease-variant set ingestion (§7.1c) `[@dwgoblue, clinical-genetics]`
18. Clinical testing intensity layer (§7.1c) `[@dwgoblue]`
19. Curated variant set definition + freeze `[needs: clinical-genetics]`
20. GCS staging + data-version pinning `[@JirachiWishmaster, infra]`

**P2 — Surface inference** `type:science` `skill:spatial-stats`
21. **Decide the INLA-SPDE runtime** (see "Flagged for Plan 2") `[needs: spatial-stats]`
22. Binomial-GP fit with `β_design`/`β_cohort` offsets `[needs: spatial-stats]`
23. Hierarchical hyperpriors by AF decile `[needs: spatial-stats]`
24. Observation-as-disc weighting by `radius_km` `[needs: spatial-stats]`
25. Data-support mask + `posterior_contraction` / `prior_dominated` `[@bschilder]`
26. Resolution-promotion thresholds, calibrated on HbS `[@bschilder]`
27. Batch orchestration over the curated set + exclusion list `[@JirachiWishmaster, infra]`

**P3 — Burden engine** `type:science` `skill:clinical-genetics`
28. Recessive / dominant / X-linked burden expressions `[@dwgoblue]`
29. Penetrance table curation `[needs: clinical-genetics]`
30. WorldPop/GPWv4 denominators → H3 `[@JirachiWishmaster, geospatial]`
31. Posterior-draw uncertainty propagation (500 draws) `[@bschilder, spatial-stats]`
32. **Golden test 1 — HbS parity** `[@bschilder]`
33. **Golden test 2 — G6PD parity (X-linked)** `[@dwgoblue]`
34. **Golden test 3 — carrier-screening parity** `[@dwgoblue, clinical-genetics]`
35. Refusal conditions verified by test `[@bschilder]`

**P4 — Tile + query backend** `type:infra` `skill:data-engineering`
36. Cloud Run + DuckDB read service `[@JirachiWishmaster]`
37. `/variants/search`, `/surface`, `/burden`, `/observations` `[@JirachiWishmaster]`
38. `/aggregate` with unmapped-fraction reporting `[@JirachiWishmaster]`
39. Resolution-laddered parquet shards + CDN `[@JirachiWishmaster, infra]`
40. BigQuery batch orchestration `[@JirachiWishmaster, infra]`
41. Variant-class policy enforced in the API, not a prompt (§16) `[@bschilder, governance]`

**P5 — Map mode UI** `type:ui` `skill:frontend`
42. Next.js 16 + deck.gl + MapLibre scaffold `[@JirachiWishmaster]`
43. Observations layer `[@JirachiWishmaster]`
44. Surface layer w/ per-frame resolution selection `[@JirachiWishmaster]`
45. Uncertainty toggle (mean vs sd, two-panel default) `[@JirachiWishmaster]`
46. Data-support mask, on by default, `unknown` vs `prior_dominated` `[@JirachiWishmaster]`
47. Burden layer + metric selector `[@JirachiWishmaster]`
48. Admin aggregation choropleth (GADM) `[@JirachiWishmaster, geospatial]`
49. Rectangle / circle / lasso selection `[@JirachiWishmaster]`
50. URL-encodable view state `[@JirachiWishmaster]`
51. Legend w/ model version + HWE assumption flag `[@bschilder, docs]`

**Public-launch track** `type:governance`
52. CONTRIBUTING, CODE_OF_CONDUCT, issue templates `[@bschilder]`
53. Position on redistributing surfaces from indigenous panels (§14.1) `[@bschilder + @ctbio123]`
54. PGG.SNV bulk-access outreach (§14.3) `[@ctbio123, partnerships]`
55. 23andMe fitted-surface proposal (§14.4) `[@bschilder, partnerships]`
56. Sponsorship wiring + FUNDING.yml `[@bschilder]`

### Task G3: Project board and automation

- Create project **"Genome OS Atlas"** under `bschilder` (`gh project create`).
- Every issue gets: one `type:*` label, one `P*:` label, one or more `skill:*` labels, a milestone (M1–M4), and a parent (except the six P-issues themselves).
- Fields: **Status** (single-select: `Backlog`, `Ready`, `In progress`, `In review`, `Done`, `Not planned`), **Sub-project** (`P0`–`P5`, `Launch`), **Skill** (mirrors the `skill:` labels), **Estimate** (number).
- Built-in workflows: *auto-add* items from `bschilder/genomeOS`; *Item reopened* → `In progress`.
- **The Done/Not-Planned split needs an Action** (`.github/workflows/project-status.yml`), because the built-in "Item closed" workflow sets only one value:

```yaml
name: project-status
on:
  issues:
    types: [closed]
jobs:
  set-status:
    runs-on: ubuntu-latest
    steps:
      - env:
          GH_TOKEN: ${{ secrets.PROJECT_TOKEN }}   # PAT with `project` scope
          PROJECT_ID: ${{ vars.PROJECT_ID }}
          STATUS_FIELD_ID: ${{ vars.STATUS_FIELD_ID }}
          DONE_OPTION_ID: ${{ vars.DONE_OPTION_ID }}
          NOT_PLANNED_OPTION_ID: ${{ vars.NOT_PLANNED_OPTION_ID }}
          ISSUE_NODE_ID: ${{ github.event.issue.node_id }}
          STATE_REASON: ${{ github.event.issue.state_reason }}
        run: |
          set -euo pipefail
          if [ "$STATE_REASON" = "not_planned" ]; then
            OPTION="$NOT_PLANNED_OPTION_ID"
          else
            OPTION="$DONE_OPTION_ID"
          fi
          ITEM_ID=$(gh api graphql -f query='
            query($project: ID!, $content: ID!) {
              node(id: $project) { ... on ProjectV2 {
                items(first: 100, query: "") { nodes { id content { ... on Issue { id } } } } } }
            }' -F project="$PROJECT_ID" -F content="$ISSUE_NODE_ID" \
            --jq ".data.node.items.nodes[] | select(.content.id==\"$ISSUE_NODE_ID\") | .id")
          gh api graphql -f query='
            mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
              updateProjectV2ItemFieldValue(input: {
                projectId: $project, itemId: $item, fieldId: $field,
                value: { singleSelectOptionId: $option }
              }) { projectV2Item { id } }
            }' -F project="$PROJECT_ID" -F item="$ITEM_ID" \
               -F field="$STATUS_FIELD_ID" -F option="$OPTION"
```

### Collaborator gaps worth naming

The roster covers data engineering (@JirachiWishmaster), genomics/AI (@dwgoblue, @bschilder) and partnerships (@ctbio123). Three roles have no owner, and two of them sit on the critical path:

- **Spatial statistician / geostatistician** — P2 is the highest-risk sub-project (issues 21–24) and nobody on the roster is an INLA/SPDE person. This is the gap most likely to stall the project.
- **Clinical geneticist** — penetrance curation (29), the curated variant set (19), and golden test 3 (34) all need someone who can defend a penetrance estimate.
- **Indigenous data governance advisor** — issues 9 and 53, needed *before* the repo goes public, not after.

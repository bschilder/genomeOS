# Explicit HGDP Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the HGDP registry adapter preserve explicitly supplied population-specific radii and provenance, refusing missing or malformed input instead of manufacturing metadata.

**Architecture:** Keep the existing P0 adapter signature and frozen output schemas. Validate a literal TSV at the source boundary, then construct and validate the canonical population and alias tables. Source qualification remains external to parsing.

**Tech Stack:** Python standard-library CSV/math, pandas, existing Pandera schemas and pytest; no dependency changes.

**Spec:** [Atlas design §§6,12,13](../specs/2026-08-22-genome-os-atlas-v1-design.md), [scientific objectives P0](../../scientific-engineering-objectives.md), [#21](https://github.com/bschilder/genomeOS/issues/21), [#219](https://github.com/bschilder/genomeOS/issues/219). This corrects the default-radius and constant-provenance implementation in the original data-foundation plan Task 3; it advances #189 WP0.

## Scientific contract

1. **Claim:** an HGDP P0 build must not invent a population's spatial extent or supporting citation.
2. **Output and evidence:** exact supplied radii and source/version locator strings survive loading and registry serialization; omitted, blank, nonfinite and invalid required values fail before output creation. Synthetic tests establish behavior, not real geographic validity.
3. **Component and interface:** `genomeos.registry.sources.hgdp.load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]`; the existing registry build CLI consumes its output.
4. **Assumptions and refusals:** inputs are curated ancestral-locality rows. The caller must establish coordinate meaning, geographic support and source evidence. This adapter neither verifies those assertions nor derives radii from coordinate ranges. P1 and later spatial benchmarks consume qualified registry artifacts; no real source row or existing artifact is promoted or rewritten by this task.

## Global Constraints

- Preserve the flat `genomeos/` layout, public adapter signature, frozen P0 schemas and CARE notice.
- Required input columns are `population`, `latitude`, `longitude`, `uncertainty_radius_km`, and `provenance`; additional well-formed columns such as `region` remain permitted.
- Preserve literal population labels and provenance, including leading zeros, whitespace within nonblank values and source/version fragments; do not apply pandas NA-token inference.
- Radii must be supplied, finite and strictly positive. Coordinates must be supplied, finite and within the existing canonical bounds.
- Missing columns, blank required cells, malformed or ragged records and duplicate column names are hard errors; no row is silently dropped or repaired.
- Preserve `location_type="ancestral"`, canonical slug generation and the existing biocultural notice. Do not reinterpret inputs as present-day residents or recruitment locations.
- Schema-valid strings and numbers do not certify source review, a sampling footprint, residency, canonical identity review or benchmark eligibility.
- Use only synthetic test data. The six-row fixture is hand-written; new radii and locators must be explicitly identified as synthetic.
- No real source acquisition, genotype/count implementation, model fitting, scientific artifact changes, dependency changes or permissive switches belong to this task.
- This work advances #21 and #219; it does not complete their scientific source-qualification requirements or close them.

## Task 1: Require explicit support at the HGDP input boundary

**Files:**
- Modify `genomeos/registry/sources/hgdp.py`: literal input validation and canonical output.
- Modify `tests/test_hgdp_source.py`: behavioral input and preservation regressions.
- Modify `tests/fixtures/hgdp_populations.tsv`: supplied synthetic radii and locators.
- Modify `tests/test_build_scripts.py`: real CLI refusal and parquet round trip.
- Modify `tests/test_gnomad_source.py`: assert the supplied synthetic radius reaches P1.
- Modify `scripts/build_registry.py`: document the changed HGDP input requirement.
- Create `docs/hgdp-registry-input.md`: input contract, migration and scientific limitations.
- Modify this plan only to record actual completed steps and evidence.

**Interfaces:** consumes the existing `POPULATIONS_SCHEMA` and `ALIASES_SCHEMA`; produces the unchanged `load(path, registry_version)` tuple. No new public abstraction or schema is needed.

- [x] **Step 1: Write and run failing behavior tests before changing production code.**

Use an explicitly synthetic input helper in `tests/test_hgdp_source.py`:

```python
def write_input(tmp_path, text):
    path = tmp_path / "populations.tsv"
    path.write_text(text, encoding="utf-8")
    return path


def test_explicit_support_and_literal_identity_are_preserved(tmp_path):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        "001\t1\t2\t2.5\tsynthetic:coordinates-v1#row-1;support-v2\n"
        "NA\t3\t4\t275\t synthetic:coordinates-v3#row-2 \n",
    )
    populations, aliases = hgdp.load(path, "0.1.0")
    assert populations["uncertainty_radius_km"].tolist() == [2.5, 275.0]
    assert populations["provenance"].tolist() == [
        "synthetic:coordinates-v1#row-1;support-v2",
        " synthetic:coordinates-v3#row-2 ",
    ]
    assert populations["population_id"].tolist() == ["hgdp-001", "hgdp-na"]
    assert aliases["label"].tolist() == ["001", "NA"]


@pytest.mark.parametrize("column", ["uncertainty_radius_km", "provenance"])
def test_missing_support_column_is_a_hard_error(tmp_path, column):
    row = {
        "population": "Example", "latitude": "1", "longitude": "2",
        "uncertainty_radius_km": "2.5", "provenance": "synthetic:row-1",
    }
    del row[column]
    path = write_input(tmp_path, "\t".join(row) + "\n" + "\t".join(row.values()) + "\n")
    with pytest.raises(ValueError, match=column):
        hgdp.load(path, "0.1.0")


@pytest.mark.parametrize("radius", ["", " ", "0", "-1", "NaN", "inf", "-inf", "1e999", "true"])
def test_invalid_radius_is_refused(tmp_path, radius):
    path = write_input(
        tmp_path,
        "population\tlatitude\tlongitude\tuncertainty_radius_km\tprovenance\n"
        f"Example\t1\t2\t{radius}\tsynthetic:row-1\n",
    )
    with pytest.raises(ValueError, match="uncertainty_radius_km"):
        hgdp.load(path, "0.1.0")
```

Run `PYTHONPATH=. python -m pytest tests/test_hgdp_source.py -q`; record the failures attributable to the old constants before implementing. Also cover blank population/provenance, nonfinite coordinates, out-of-range coordinates, duplicate/invalid slugs, duplicate headers, missing/extra row fields and an embedded blank record. Expected canonical schema violations may raise `pandera.errors.SchemaError`; adapter parsing/value failures raise `ValueError`. Do not assert source text or private helper implementation.

- [x] **Step 2: Implement the boundary, preserving the established output contract.**

Remove `DEFAULT_RADIUS_KM` and `PROVENANCE`, add `csv`, `math` and the public schema imports. Keep `SOURCE`, `BIOCULTURAL_NOTICE` and `slugify`. Use the following concrete implementation, adjusting formatting to repository conventions:

```python
def _read_input(path: Path) -> pd.DataFrame:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t", strict=True)
        try:
            header = next(reader, None)
            if header is None:
                raise ValueError(f"{path}: missing TSV header")
            if len(header) != len(set(header)) or any(not name.strip() for name in header):
                raise ValueError(f"{path}: duplicate or blank column names")
            required = {
                "population", "latitude", "longitude",
                "uncertainty_radius_km", "provenance",
            }
            missing = required - set(header)
            if missing:
                raise ValueError(f"{path}: missing required columns {sorted(missing)}")
            rows = []
            for row in reader:
                if len(row) != len(header):
                    raise ValueError(f"{path}: wrong field count at line {reader.line_num}")
                rows.append(row)
        except csv.Error as exc:
            raise ValueError(f"{path}: malformed TSV at line {reader.line_num}") from exc
    return pd.DataFrame(rows, columns=header, dtype=str)


def load(path: Path, registry_version: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = _read_input(path)
    for column in ("population", "latitude", "longitude", "uncertainty_radius_km", "provenance"):
        if raw[column].str.strip().eq("").any():
            raise ValueError(f"{path}: blank required value in {column}")
    numeric = {}
    for column in ("latitude", "longitude", "uncertainty_radius_km"):
        try:
            values = raw[column].astype(float)
        except ValueError as exc:
            raise ValueError(f"{path}: invalid numeric value in {column}") from exc
        if not values.map(math.isfinite).all():
            raise ValueError(f"{path}: nonfinite value in {column}")
        numeric[column] = values
    if (numeric["uncertainty_radius_km"] <= 0).any():
        raise ValueError(f"{path}: uncertainty_radius_km must be strictly positive")
    ids = raw["population"].map(slugify)
    populations = pd.DataFrame({
        "population_id": ids,
        "lat": numeric["latitude"],
        "lon": numeric["longitude"],
        "uncertainty_radius_km": numeric["uncertainty_radius_km"],
        "location_type": "ancestral",
        "provenance": raw["provenance"],
        "biocultural_notice": BIOCULTURAL_NOTICE,
        "registry_version": registry_version,
    })
    aliases = pd.DataFrame({"population_id": ids, "source": SOURCE, "label": raw["population"]})
    return POPULATIONS_SCHEMA.validate(populations), ALIASES_SCHEMA.validate(aliases)
```

The module docstring must cite design §§6,12,13 and state that source qualification precedes this parser. Explain that this is curated input, not an untouched vendor export. Do not call a parsed row reviewed or scientifically eligible.

- [x] **Step 3: Update the synthetic fixture and document migration.**

Append `uncertainty_radius_km` and `provenance` columns to the existing six rows, keeping their labels, coordinates and regions unchanged. Use radii `2.5`, `5`, `25`, `75`, `125`, `250` in existing row order and locators `synthetic:hgdp-fixture-v1#row-1` through `synthetic:hgdp-fixture-v1#row-6`. These are hand-written test values, not measured or inferred extents of the named populations.

In `docs/hgdp-registry-input.md`, document the five-column input with a fictional `Example` row (radius `2.5`, provenance `synthetic:example-v1#row-1`), optional `region`, literal string preservation, refusals and unchanged output schema. Explain that `provenance` must identify the supporting coordinate/support source and version; multiple locators can share this existing string field. Parsing does not inspect those sources. Existing four-column files now fail and must be curated with supporting evidence; no conversion command or default-fill recipe is offered. Explicitly identify the six-row test fixture as synthetic and preserve the open scientific work under #21/#219.

Add a short pointer to this guide in the build-script docstring and `--hgdp` help. Add a supersession note to the original data-foundation plan Task 3 pointing to this plan/guide, without rewriting its historical implementation example. This is the only additional file permitted beyond the file map above.

- [x] **Step 4: Verify the actual build boundary and downstream consumers.**

In `tests/test_build_scripts.py`, run the actual `scripts/build_registry.py` via `sys.executable`, `cwd=ROOT`, with the checkout explicitly on `PYTHONPATH`. Add a subprocess test for the legacy four-column input: nonzero exit, an error naming the two missing columns, and no new output directory. Add a successful fixture-backed build test reading both generated Parquet files: assert six rows, radii `[2.5, 5.0, 25.0, 75.0, 125.0, 250.0]`, exact synthetic locators and original aliases. Keep assertions independent of production constants and read actual serialized output.

In `tests/test_gnomad_source.py::test_coordinates_and_radius_come_from_the_registry`, replace the obsolete `pytest.approx(50.0)` expectation with `pytest.approx(2.5)`, the literal synthetic Yoruba fixture radius. Preserve the coordinate assertion and all other observation tests; no P1 implementation changes are required.

Run `PYTHONPATH=. python -m pytest tests/test_hgdp_source.py tests/test_registry_schema.py tests/test_registry_build.py tests/test_gnomad_source.py tests/test_afnd_source.py tests/test_build_scripts.py -q` and the mandatory `python scripts/smoke.py`. Record commands, results, failures and warnings exactly. Do not broaden unrelated tests while iterating.

- [x] **Step 5: Complete reviewable delivery.**

Run full CI commands once after implementation: `ruff check .`, `python scripts/freeze_contract.py --check`, `python scripts/check_module_size.py`, `python scripts/check_private_files.py`, `python scripts/smoke.py`, and `pytest`. Record the actual source/environment and results. Inspect `git diff --cached --name-only` and run the privacy gate immediately before committing. Stage only the files named by this plan and commit `fix: require explicit HGDP support and provenance; refs #21, #219` on the isolated branch. Do not push; the controller performs independent review and PR delivery after verifying the result. Real data and all private task artifacts stay untracked.

## Controller preflight

One task owns the adapter, fixture, documentation and executable build tests; there is no cross-task interface handoff. Supplied values are preserved, not certified. Canonical schemas, real registry artifacts and the active model calibration are outside the change. A figure is not produced because this task creates no scientific observation/surface or changed rendered artifact.

## Implementation record — 2026-09-11

- Source: isolated worktree `/private/tmp/genomeos-hgdp-explicit-support-20260911`, based on
  `3c986902c12b40b84c56145ed863f7f519cbab6b`. Import provenance printed
  `/private/tmp/genomeos-hgdp-explicit-support-20260911/genomeos/__init__.py`.
- RED: the locked interpreter running `PYTHONPATH=. python -m pytest
  tests/test_hgdp_source.py -q` reported `4 passed, 35 failed`; failures showed the old constant
  support/provenance, pandas identity inference, missing refusal paths and absent schema validation.
  The two new registry CLI tests both failed against the old behavior. The existing direct P1
  propagation test then failed with an obtained fixture radius of `2.5` against its obsolete
  `50.0` expectation.
- GREEN: the same locked focused source command passed all 40 cases. Both registry CLI tests passed,
  and the required six-file focused suite passed with no warnings. `python scripts/smoke.py` passed
  all 40 smoke checks.
- Final: lint (shown here in portable form as `.venv/bin/ruff check .`), frozen-contract check,
  module-size check, privacy check and smoke all exited 0. The full locked `python -m pytest`
  completed with `571 passed, 5 warnings in 297.98s`; the warning summary named the two
  cross-validation coverage tests, while the task-focused suite emitted no warnings.
- Scope: no schema, dependency, real-data, P1 implementation, model, or artifact change. The fixture
  radii and locators are synthetic and do not qualify any HGDP row.

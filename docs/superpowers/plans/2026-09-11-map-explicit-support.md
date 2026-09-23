# MAP explicit spatial support implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove automatic MAP area-to-radius inference so a raw survey export cannot silently acquire qualified spatial precision.

**Architecture:** Keep `map_surveys.load` and its P1 output contract. It consumes a separately retained curated CSV with explicit bounding-disc support and evidence locators. Raw exports remain raw evidence. Validate support before any surviving row becomes a P1 observation; fitting, serving and scientific source review remain separate responsibilities.

**Tech stack:** Existing Python, pandas, pandera and Matplotlib; no dependency or frozen P1 schema change.

**Spec:** [Issue190](https://github.com/bschilder/genomeOS/issues/190), including its equal-area-versus-bounding-radius clarification; Atlas design §§4–8,12; scientific-engineering objectives P0/P1; WP0/WP1 of the global modeling program. The original data-foundation Task7's fixed-radius example is superseded by the no-default invariant and issue190.

## Scientific contract

1. **Claim:** every MAP radius emitted by this adapter is explicitly supplied under a sampling bounding-disc contract, never inferred from an area class or a missing value. Parser acceptance does not establish that supplied evidence is true, independently reviewed, representative of residents, or eligible for publication.
2. **Output/evidence:** same schema-valid P1 rows and count-refusal report for curated synthetic inputs; hard errors for otherwise-retainable rows missing valid explicit support; raw area-only exports fail. Regression, CLI, round-trip and export tests prove those boundaries. A synthetic figure illustrates accepted versus unavailable geographic support; no real source is promoted.
3. **Component/interface:** `genomeos.observations.sources.map_surveys.load(path, ingest_version, *, piel_2013_subset_only=False, min_genotyped_fraction=DEFAULT_MIN_GENOTYPED_FRACTION) -> tuple[pd.DataFrame, IngestReport]` stays unchanged. New required CSV columns are `radius_km`, `support_kind`, `coordinate_provenance`, `radius_provenance`.
4. **Assumptions/refusals/consumers:** `support_kind` must be exactly `sampling_bounding_disc`; the radius bounds recruitment support relative to the row's WGS84 coordinate. Area, equivalent-area radius, administrative area and presumed catchment do not satisfy this declaration. Both provenance strings must be nonblank locators to the coordinate interpretation and radius evidence/derivation. Evidence review occurs before a real curated input is approved. Missing or invalid support is a hard input error, not a radius fallback or a quietly omitted measurement. The eight existing script consumers keep their interfaces and require this curated input for HbS. Existing raw source bytes and published artifacts remain unchanged.

## Global constraints

- No default, assumed, inferred-from-area or override radius. No `force`, permissive, auto-curation or eligibility switch.
- No real coordinates, radii, provenance, reviewer or qualification status may be invented. Keep the existing real MAP fixture unchanged. New positive examples are wholly synthetic and conspicuously labeled as such.
- Preserve count reconstruction, genotype thresholds, denominator arithmetic, cohort construction, Piel-subset behavior and count-refusal accounting. This task neither changes nor scientifically endorses those independent assumptions.
- No fitting, calibration change, source acquisition, new data export, production rebuild or mutation of existing artifacts. No serving schema or scientific gate changes.
- Keep pure domain logic free of I/O; the existing source adapter remains the I/O boundary. Do not introduce a general evidence framework or a registry dependency for MAP.
- Each new production module cites the relevant design sections, uses `from __future__ import annotations`, and stays within the existing module-size gate. No stochastic path is added.
- All verification must import this worktree explicitly. Use the existing locked interpreter with `PYTHONPATH=.` and explicit writable task caches, confirmed before imports. Retain failures and unsuppressed warning output.
- Public files use portable paths. Keep private execution paths, logs and task instructions in this plan's ignored workspace. Never stage `.superpowers/`, `.codex/`, `.agents/`, raw data, credentials or history.
- One coherent implementation task, one task review, and a fresh full-branch review. Preserve the worktree and evidence after completion. Branch/push/PR are already authorized by repository instructions; no merge is authorized here.

## Task 1: Enforce explicit MAP support through existing ingestion consumers

**Files:**

- Modify `genomeos/observations/sources/map_surveys.py`.
- Create `tests/fixtures/map_hbs_curated_synthetic.csv` and its focused `tests/fixtures/map_hbs_curated_synthetic.README.md`.
- Modify `tests/test_map_surveys.py`, `tests/test_ingest_observations.py`, `tests/test_build_scripts.py`, `tests/test_export_atlas_web.py`.
- Update HbS examples/help only in `scripts/build_observations.py`, `scripts/build_surfaces.py`, `scripts/publish_artifacts.py`, `scripts/validate_holdout.py`, `scripts/plot_fold_strategies.py`, `scripts/plot_observations.py`, `scripts/plot_surface.py`, `scripts/export_atlas_web.py`.
- Create `docs/map-spatial-support.md`, `scripts/plot_map_support_contract.py` and `docs/figures/map_support_contract.png`.
- Update the runnable fixture command in `AGENTS.md` and current workflows in `docs/data-store.md`; retain raw fetch commands and historical source paths as raw-source documentation. Include this plan in the task commit.

**Interfaces:** existing loader arguments/return type, P1 schema, script flags and export JSON schema remain unchanged. A curated CSV replaces an untouched vendor CSV at each HbS input boundary. The loader must preserve the exact explicit radius; it must not recalculate it when area_type changes.

### 1. Preserve the old evidence and create an honest positive fixture

- [ ] Keep `tests/fixtures/map_hbs_surveys.csv` byte-for-byte unchanged. Test that this area-only export now raises an actionable `ValueError` naming missing explicit support columns and the curated-input requirement.
- [ ] Add the new synthetic CSV. Use fictional survey IDs9001–9011, fictional study IDs prefixed `SYNTHETIC-`, `country=Synthetic`, `citation=Synthetic contract example; not a publication`, and provenance locators `synthetic:map-support#<id>-coordinate` / `synthetic:map-support#<id>-radius`. These locators identify authored test evidence, never a real review or scientific source. Use fixed coordinates within WGS84 bounds, varied positive declared radii, and a mix of empty, unrecognized and original area-class tokens. All support kinds are `sampling_bounding_disc` in the positive fixture. Do not reuse real survey IDs or geographic claims.

Required count cases (HbAA/HbAS/HbSS, sample_size):

| ID | Counts | Sample | Expected existing count behavior |
|---|---|---:|---|
|9001|20/4/1|25|complete, AC6 AN50|
|9002|34/5/1|50|partial, AC7 AN80|
|9003|10/0/0|10|zero count retained|
|9004|9/1/blank|10|HbSS derived as0|
|9005|blank/2/1|10|HbAA reconstructed as7|
|9006|5/2/1|7|small excess retained, AN16|
|9007|30/0/0|10|genotypes_exceed_sample|
|9008|blank/1/blank|10|incomplete_genotypes|
|9009|1/1/0|100|screen_positives_only|
|9010|10/0/0|10|missing_coordinates; leave latitude blank|
|9011|20/5/0|25|population_estimates=NO; otherwise valid|

Set population_estimates=YES for other rows. The README lists every authored radius/coordinate and states no real MAP support was reviewed or inferred. Update positive integration fixtures to this synthetic source. Preserve the old count-regression meanings using the cases above; do not delete the meaningful checks because the input contract changed.

### 2. Record failing tests for the precise defect

- [ ] Before editing production code, execute focused regressions and retain expected failures. Include:

```python
def test_raw_area_only_export_requires_explicit_support():
    with pytest.raises(ValueError, match="explicit spatial support"):
        map_surveys.load(RAW_FIXTURE, "test")

def test_explicit_radius_is_preserved_when_area_label_changes(tmp_path):
    frame = pd.read_csv(CURATED_FIXTURE)
    frame.loc[frame.id == 9001, "radius_km"] = 73.25
    frame.loc[frame.id == 9001, "area_type"] = "Large polygon (>100 km2)"
    path = tmp_path / "curated.csv"
    frame.to_csv(path, index=False)
    obs, _ = map_surveys.load(path, "test")
    assert obs.set_index("source_record_id").loc["map-surveys:9001", "radius_km"] == 73.25
```

- [ ] Parameterize each missing support column, blank coordinate/radius provenance, kind values `equal_area_disc`, `ancestral_bounding_disc`, blank and unknown, and radii0/negative/NaN/infinite/non-numeric/boolean tokens. Each otherwise-retainable row must raise `ValueError` naming its native survey ID and defective field. Duplicate support headers are hard errors before pandas can mangle names. A bounded area token cannot rescue any invalid support case.
- [ ] A count-refused row may lack per-row spatial values, since it never enters P1; the required columns must still exist. Preserve the existing count reason and total accounting. A malformed support value on a surviving row must fail the entire call, never yield a partial success report.
- [ ] Verify exact typed-denominator arithmetic, zero retention, both reconstructions, small/gross excess, missing counts/coordinates, Piel subset, invalid genotype fraction and report reconciliation on the new fixture.

### 3. Implement the narrow input boundary

- [ ] Remove `_AREA_KM2_UPPER`, `_UNBOUNDED_AREA`, `_UNBOUNDED_AREA_KM2`, `_UNKNOWN_AREA_KM2` and `_radius_km` and their unsupported comments. Area labels remain preserved input evidence but have no effect on emitted radius.
- [ ] Require the four support columns with a diagnostic containing `explicit spatial support` and all missing names. Check duplicate headers before `pd.read_csv` can silently rename them; use the stdlib CSV reader for this header check. Do not redesign unrelated count parsing.
- [ ] After existing count/subset refusals determine `keep`, validate support only for those surviving rows. Parse declared radius to finite positive float, rejecting boolean values/tokens, and require exact kind plus nonblank textual provenance. Raise on the first invalid row with field and native ID; no coercive default or partial frame.
- [ ] Assign the validated radius aligned to retained rows. A small private helper in this adapter is sufficient; no new public configuration or validator framework. Implement the following semantics, adapting names to surrounding style:

```python
SUPPORT_COLUMNS = {"radius_km", "support_kind", "coordinate_provenance", "radius_provenance"}

def _explicit_radii(rows: pd.DataFrame) -> pd.Series:
    values = []
    for row in rows.itertuples(index=False):
        if row.support_kind != "sampling_bounding_disc":
            raise ValueError(f"MAP survey {row.id}: invalid support_kind; explicit spatial support required")
        for field in ("coordinate_provenance", "radius_provenance"):
            value = getattr(row, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MAP survey {row.id}: blank {field}; explicit spatial support required")
        raw_radius = row.radius_km
        if isinstance(raw_radius, bool) or str(raw_radius).strip().lower() in {"true", "false"}:
            raise ValueError(f"MAP survey {row.id}: invalid radius_km")
        try:
            radius = float(raw_radius)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"MAP survey {row.id}: invalid radius_km") from exc
        if not math.isfinite(radius) or radius <= 0:
            raise ValueError(f"MAP survey {row.id}: radius_km must be finite and positive")
        values.append(radius)
    return pd.Series(values, index=rows.index, dtype=float)
```

This is a behavioral skeleton, not permission to duplicate validation or ignore pandas nullable scalars. Handle pandas missing values explicitly so refusal is a `ValueError`, not an ambiguous-boolean crash. Validate enum/locators as strings. Report parser acceptance as structural only.

### 4. Migrate workflows without fabricating a real curated source

- [ ] Keep the eight loader call sites and public signatures intact. Update help/docstrings to say HbS requires a curated MAP CSV with explicit spatial support. Use `data/curated/map_hbs_surveys.csv` as an illustrative future operator-provided path, and the new synthetic fixture for runnable demonstrations. Do not create that real curated file or claim it exists.
- [ ] Integration tests must show the curated fixture survives Parquet round-trip and web export with its exact declared radius, source IDs and existing evidence fields. Test build-observations with the original raw fixture: nonzero exit, clear support diagnostic, no output store created. Test web export with support omitted: explicit failure before any success catalog is written. Existing publication/fit artifacts are never rewritten by these tests or this task.
- [ ] `docs/map-spatial-support.md` defines fields, failure behavior, equal-area versus bounding radius, preservation of raw input and immutable versioned curated evidence, source qualification versus structural validation, separate #37 likelihood work, and the continued count/ascertainment limitations. Explain that untouched vendor exports now intentionally fail. Provenance stays in retained curated source evidence; unchanged P1/schema/export does not purport to carry or verify the entire evidence ledger.
- [ ] Update current data-store workflow and AGENTS runnable fixture command. Do not rewrite historical execution records or claim the new input contract alone qualifies historical maps.

### 5. Show the changed observation contract and verify

- [ ] Add a small offline `scripts/plot_map_support_contract.py --out NEW_PNG` over the synthetic fixture. Use the actual loader to obtain accepted points. Show synthetic survey positions on a geographic axis, exact declared radii as text labels, and explicitly hatched/unqualified space elsewhere. A separate panel states that the area-only version is refused and emits no P1 observations; invoke the actual loader on a temporary copy without support columns to establish that result. Do not infer/draw a fitted frequency surface or manufacture a precise circle in degree coordinates. Mark the whole figure `SYNTHETIC — contract demonstration, not scientific results`. Refuse existing output paths.
- [ ] Generate `docs/figures/map_support_contract.png`, inspect it visually, and document its exact reproduction command. The figure contains no real survey data and requires no network source acquisition.
- [ ] Run focused tests for the touched behavior,40-check smoke, Ruff, frozen-contract check, module size, privacy and whitespace; run the full suite once on the final implementation. Preserve complete output and all warnings. No gate/tolerance/fixture weakening to make tests pass. No full rerun for an unchanged tree; fix-driven reruns cover changed behavior.
- [ ] Self-review full task diff; verify original real fixture hash unchanged, exact staged paths, no personal/private paths in public files, no new real data or artifacts. Before commit run the privacy gate and inspect staged names. Commit `fix: require explicit MAP spatial support; closes #190` on the task branch. This closes the automatic-radius defect, not source qualification, #37 or #189.
- [ ] Write the full report to the controller-provided private path: implementation, exact RED/GREEN commands/results, all gates/full-suite counts/warnings, figure inspection, changed files, retained source hash, self-review and concerns. Return only status, commit, concise verification and report path. Do not spawn any subagents, push, merge or create a PR; the controller handles independent reviews and delivery.

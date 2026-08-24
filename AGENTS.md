# genomeOS — conventions for agentic contributors

Most contributions to this repository are made by coding agents. This file is the contract.
Read it fully before writing code; it is short on purpose.

## Read first

1. [`docs/overview.md`](docs/overview.md) — what the project is and why. Non-negotiable context.
2. [`docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md`](docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md)
   — the Atlas design. **Cite the section you are implementing in your module docstring**, e.g.
   `design §7.1`.
3. The plan for your sub-project, e.g.
   [`docs/superpowers/plans/2026-08-22-atlas-data-foundation.md`](docs/superpowers/plans/2026-08-22-atlas-data-foundation.md)
   (P0 + P1). Plans are task-by-task with tests specified; follow them rather than improvising.
4. [Issue #3](https://github.com/bschilder/genomeOS/issues/3) if you are touching data ingestion —
   it explains what every source is for and what its access terms are.
5. [`docs/panukb-architecture.md`](docs/panukb-architecture.md) if you are touching `genomeos/`.

## Check the issues before you start — open *and* closed

The [issue tracker](https://github.com/bschilder/genomeOS/issues) is the project's record of what
has been done, what was decided and why, and what still needs doing. Search it before writing
anything.

```bash
gh issue list --state all --search "registry adapter"   # or the GitHub UI
```

- **Open issues are the work queue** — 64 of them across 4 milestones, each with a sub-project,
  a skill, and a priority. Everything planned for v1 is already logged.
- **Closed issues carry the decisions.** Closed as *completed* means the work exists — read it
  rather than redoing it, and note that its approach is probably the house pattern. Closed as
  *not planned* means it was considered and rejected; reopening that needs an argument in the
  issue, not a fresh PR.
- If what you are about to do has no issue, that is a signal. Either you have found a genuine
  gap — file it — or the work is out of scope.

## Filing work

- **Found a bug?** Open an issue. Include what you ran, what happened, and what you expected. If
  it breaks an invariant below, say which one.
- **Want a new feature?** **Open an issue first and let it be triaged** — do not arrive with an
  unrequested feature PR. Priority here is derived from the dependency graph, so unscheduled
  features displace critical-path work even when they are good ideas. Check the deferred list in
  [`docs/overview.md`](docs/overview.md) first: P6–P12 are deliberately out of scope for v1, and
  their absence is a decision rather than an oversight.
- **Improving the design, the dataset scores in
  [#3](https://github.com/bschilder/genomeOS/issues/3), or the statistics?** Very welcome — comment
  on the relevant issue or open a new one.
- New issues are auto-added to the board as `Backlog`. Apply the four label families if you can;
  if you cannot, say so in the issue body so it can be triaged.

## Invariants

Violating one of these is a bug, not a style choice. They exist because the failure modes they
prevent are documented and expensive (design §4).

- **Observations and surfaces are never conflated.** Observations are measured; surfaces are
  inferred. Separate tables, separate layers, separate provenance. No code path may produce a
  view where a user cannot tell which is which. (§4, §5)
- **No inference on the serving path.** All fitting is offline and batch. The read API reads
  precomputed artifacts and aggregates them; it never computes science. (§5)
- **Schema violations are hard errors.** Never silently drop a row, coerce a bad value, or
  substitute a default. A population label with no coordinate must fail the build loudly. (§12)
- **`uncertainty_radius_km` has no default. The ascertainment fields
  (`sampling_design`, `disease_ascertainment_excluded`, `cohort_id`) have no defaults.** A source
  adapter that cannot supply them is incomplete, not ready to merge. (§6, §7.1)
- **Artifacts are immutable**, keyed by `(variant_id, model_version, data_version)`. A model
  change publishes new artifacts; it never mutates a map someone has cited. (§5)
- **Masked cells (`unknown`, `prior_dominated`) are excluded from every aggregation statistic**,
  and the excluded fraction is returned with the result. (§7, §10)
- **The variant-class policy is enforced server-side.** Behavioural, cognitive and anthropometric
  traits are ineligible for burden rendering, for every caller. Never move this check into a
  prompt, a client, or a config flag. (§13)
- **Science modules carry no HTTP or I/O dependency**, so they unit-test directly against
  published numbers. Thin wrappers do the serving.
- **Determinism.** `SEED = 42` in any module with a stochastic path. Offline functions must be
  deterministic given `(config, data_version, seed)`.

## Deliberate behaviours — do not "fix" these

These look like missing error handling or missing defaults. They are the design. Changing any of
them requires an issue and a decision, not a commit.

| Looks like | Actually is |
|---|---|
| `genomeos/ingest.py` refuses generic `pval_*` columns unless given an explicit encoding | **Fail-closed by design.** Pan-UKB's own documentation contradicts itself about whether files carry `ln(p)` or `-log10(p)`. A "sensible default" here silently mis-scales every p-value. |
| Required fields with no fallback value | See the invariants. A missing coordinate or ascertainment design must break the build. |
| The pipeline emitting *no* number for a cell | A **refusal**, and a valid output. Emitted when support is `unknown`, no penetrance estimate exists, or no population denominator exists. (§9) |
| Bounded list endpoints, no bulk export, no arbitrary SQL | Deliberate. Full-matrix exports are not REST operations; ~7,228 phenotypes × 29M variants must never be flattened into rows. |
| Region queries disabled by default (`PANUKB_REGION_QUERY_ENABLED`) | Feature-flagged on purpose, with a row cap. |

## Repository layout

**Current state.** `genomeos/` is the Pan-UKB evidence API — a flat package installed with
setuptools. It is the trait and effect-size layer of the atlas (category E in #3), and it works.

**Planned state.** The Atlas data foundation lands as `src/genomeos/` with `uv`, `pandera`
schemas frozen into `contract/`, `ruff`, and `pyright` — specified in Plan 1, Task 1. **That
migration has not happened.** Do not partially migrate the repo as a side effect of another
task, and do not "fix" the current layout to match the plan unless you are working Task 1.

## Commands

Current, and what CI must keep passing:

```bash
python -m pip install -e '.[dev]'   # add [postgres] or [tabix] as needed
genomeos init-db
uvicorn genomeos.api:app --reload
pytest
```

`sqlite:///./genomeos.db` is the local default; production requires a PostgreSQL `DATABASE_URL`.
GCP operations must go through the [repository-local gcloud wrapper](docs/repo-gcloud-auth.md) —
never bare `gcloud`.

Once the Atlas package lands: `uv sync` · `uv run pytest` · `uv run ruff check` · `uv run pyright`.

## Code conventions

Match the surrounding code. Observed and expected:

- `from __future__ import annotations` at the top of every module.
- SQLAlchemy 2.0 typed style: `Mapped[...]` with `mapped_column`. Pydantic v2 with
  `ConfigDict(from_attributes=True)` for response models.
- API handlers are thin and directly callable — tests import them from `genomeos.api` and call
  them with a session rather than going through HTTP. Keep them that way.
- Test fixtures are tiny, checked in under `tests/fixtures/`, and readable by eye.
- Module docstrings cite the design section they implement.
- Comment density, naming, and idiom should be indistinguishable from the file you are editing.

## Data and access terms

These are hard constraints, not preferences:

- **All of Us data may inform models but may never be served by our backend** — it cannot leave
  the Researcher Workbench.
- **Redistribution of derived surfaces from indigenous-population panels is an open question**
  ([#66](https://github.com/bschilder/genomeOS/issues/66)). Do not publish or commit derived
  artifacts from HGDP, SGDP, AADR or AFND as standalone datasets until it is answered.
- Registry entries carry provenance and a Biocultural Notice field, per the CARE Principles.
  Never drop these columns for convenience.
- Check the licence before ingesting. gnomAD is CC0, but its bundled SpliceAI annotations are
  CC BY-NC.

## Working the board

- Every issue carries `type:*`, `P*:` (sub-project), `skill:*`, and `priority:*` labels.
  Conventions in [`docs/board-conventions.md`](docs/board-conventions.md).
- **Status `Ready` means fully specified and unblocked — take it without asking.**
- `wants-expert-review` means an agent implements it and a domain expert should review after.
  Implement it, and say explicitly in the PR what an expert should check.
- `needs-human-decision` means a person must commit on the project's behalf. **Do not decide it
  yourself** — surface the options and stop.
- Priority is derived from the dependency graph, not enthusiasm. `critical` blocks other work or
  *is* the definition of done.

## Pull requests

**Every change to this repository goes through a pull request — code, docs, config, all of it.
Nothing is committed directly to `main`.**

- **Branch, push, open a PR.** One PR per task or coherent unit of work.
- Reference the issue you are closing, and say which design sections you implemented.
- State what you verified and how. If a test fails or you skipped part of the scope, say so
  plainly with the output — an unverified claim of completion is worse than an honest partial.
- Do not widen scope silently. If you find a real problem outside your task, **open an issue**
  and keep going on the task you were given.
- Commit messages: `type: summary` (`docs:`, `feat:`, `fix:`, `chore:`, `ci:`), imperative mood.
- Closing a PR closes its issue and the board automation routes the status: closed as *completed*
  → `Done`, closed as *not planned* → `Not planned`, reopened → `In progress`. Close issues with
  the right reason so the board stays truthful.

## Definition of done

For the Atlas, correctness means **reproducing published science**, not producing plausible
output. Golden tests 1–3 (HbS parity, G6PD parity, carrier-screening parity) gate publication of
every other variant's burden layer (§8). Never weaken a golden test to make a build pass; if it
fails, the pipeline is wrong.

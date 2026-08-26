# genomeOS — conventions for agentic contributors

Most contributions to this repository are made by coding agents. This file is the contract.
Read it fully before writing code; it is short on purpose.

## Read first

1. [`docs/overview.md`](docs/overview.md) — what the project is and why. Non-negotiable context.
2. [`docs/scientific-engineering-objectives.md`](docs/scientific-engineering-objectives.md) —
   the scientific claims, engineering deliverables, interfaces, and acceptance evidence for P0–P5.
3. [`docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md`](docs/superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md)
   — the Atlas design. **Cite the section you are implementing in your module docstring**, e.g.
   `design §7.1`.
4. The plan for your sub-project, e.g.
   [`docs/superpowers/plans/2026-08-22-atlas-data-foundation.md`](docs/superpowers/plans/2026-08-22-atlas-data-foundation.md)
   (P0 + P1). Plans are task-by-task with tests specified; follow them rather than improvising.
5. [Issue #3](https://github.com/bschilder/genomeOS/issues/3) if you are touching data ingestion —
   it explains what every source is for and what its access terms are.
6. [`docs/panukb-architecture.md`](docs/panukb-architecture.md) if you are touching the
   Pan-UKB evidence slice.

## Scientific contract before implementation

Every task must state four things before methods are chosen:

1. the scientific objective or product claim;
2. the measurable output and acceptance evidence;
3. the engineering component and public interface that produce it;
4. the assumptions, refusal conditions, and downstream consumers.

Prefer the smallest implementation or experiment that can reject or support the claim. A model
metric without a scientific interpretation target is not an objective. Never silently substitute
a dataset, method, coordinate, default, or success criterion when the specified one is unavailable.

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

## Module and configuration boundaries

- Each module has one scientific or engineering responsibility and an explicit typed interface.
  Dependencies point inward toward schemas and domain functions; orchestration, storage, HTTP,
  and UI remain adapters around them.
- Connect modules through versioned schemas or artifact contracts, not imports of private
  implementation details. Keep observations, surfaces, burden, serving, and rendering independently
  replaceable.
- Configuration enters at composition boundaries through typed settings or explicit function
  arguments. Do not read environment variables, global state, networks, or files from pure science
  modules. Do not add a config switch for a scientific or governance invariant.
- Avoid optional abstractions, registries, factories, and fallback paths until two real consumers
  require them. Modularity means narrow contracts, not more layers.
- Keep files agent-readable. Target at most 500 logical lines per production module. At 800 lines
  or 50 KiB, split by responsibility before adding features unless a documented reason makes the
  split less coherent. Generated files and frozen contracts are exempt. Run
  `python scripts/check_module_size.py`.
- A module must be understandable from its docstring, public types/functions, and directly relevant
  tests without loading the whole repository. If not, narrow the module or add a short focused design
  note; do not compensate with a larger prompt.

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

One installable package, `genomeos/`, holding both workstreams:

```
genomeos/
  api.py cli.py db.py ingest.py models.py schemas.py tabix.py   # Pan-UKB evidence API
  registry/      schema.py build.py sources/                    # P0 — population registry
  observations/  schema.py ingest.py sources/                   # P1 — observations store
  surfaces/      fit.py mask.py                                 # P2 — surface inference
  burden/        expressions.py propagate.py                    # P3 — burden engine
  validation/    hbs_parity.py                                  # golden tests (§8)
  reference/     piel2013.py                                    # published parity targets
  geo/           h3util.py population.py                        # H3 indexing, denominators
contract/        *.schema.json      # frozen pandera schemas; CI fails on drift
scripts/         build_registry.py build_observations.py freeze_contract.py
```

**Note for anyone reading the plans:** Plan 1 specifies `src/genomeos/` with `uv` and hatchling,
because it was written when the repo was empty. The Pan-UKB service landed first, and moving it
to a `src/` layout would have broken a deployed container for no design benefit — the import
paths are identical either way. The Atlas modules are therefore subpackages of the flat
`genomeos/` package. **Do not migrate the layout** as a side effect of another task.

The heavy Atlas dependencies (pandera, pandas, pyarrow, duckdb, h3) live in the `atlas` extra,
PyMC/PyTensor in a `surfaces` extra, and rasterio in a `geo` extra, so the API container carries
none of them. Install everything with `.[dev,atlas,surfaces,geo,figures]`.

**Inference engine:** PyMC with a Hilbert-space GP (HSGP), *not* R-INLA-SPDE, despite what
design §7 names. The reasoning and the rejected alternatives are in #34; do not reintroduce an R
toolchain without reopening that decision.

## Commands

Current, and what CI must keep passing:

```bash
python -m pip install -e '.[dev,atlas,surfaces,geo,figures]'   # add [postgres] or [tabix] as needed
ruff check .                              # lint; CI runs this
python scripts/freeze_contract.py --check # contract drift; CI runs this
python scripts/check_module_size.py        # agent-readable module budget; CI runs this
python scripts/check_private_files.py      # tracked-file privacy gate; CI runs this
python scripts/smoke.py                    # mandatory fast verification; CI runs this
pytest                                    # CI runs this

genomeos init-db                          # Pan-UKB API
uvicorn genomeos.api:app --reload
python scripts/http_smoke.py --base-url http://127.0.0.1:8000  # live API + preview proof
```

The fixture-backed diagnostic preview is at `/preview`. It proves the P4 read path only and is
not the P5 product UI. Demo artifacts are synthetic, mounted read-only in containers, and must
never be presented as scientific results.

Rebuild the Atlas stores from fixtures (the end-to-end check):

```bash
python scripts/build_registry.py --hgdp tests/fixtures/hgdp_populations.tsv --out data/registry
python scripts/build_observations.py --registry data/registry \
  --gnomad tests/fixtures/gnomad_hgdp_1kg_freqs.tsv \
  --map-surveys tests/fixtures/map_hbs_surveys.tsv --out data/observations
```

**If you change a schema, run `python scripts/freeze_contract.py` and commit the `contract/`
diff.** That diff is the review surface for schema change; CI fails if it is stale.

### Reproducing the environment exactly

The bounds in `pyproject.toml` are ranges, so two contributors following the install line above
can end up on different versions of the libraries that decide behaviour. That is not theoretical:
`pymc>=5.16` resolved to **6.3.1**, and PyMC changed how NUTS options are passed between 5.x and
6.x — enough for two people to disagree about what the code does while both being right about
their own environment. Upper bounds are now declared for the libraries this has bitten.

`requirements.lock` pins every package exactly, generated universal so it installs on macOS, on
Linux CI and on a pod:

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -r requirements.lock
python -m pip install -e '.' --no-deps
```

Regenerate it when a dependency changes, and commit the diff:

```bash
uv pip compile pyproject.toml --universal --extra dev --extra atlas --extra surfaces \
    --extra geo --extra figures --python-version 3.12 --output-file requirements.lock
```

**Before arguing about library behaviour, run `python scripts/env_report.py`.** It prints the
installed versions and then *empirically* shows where NUTS options land in your environment, by
spying on `sample_jax_nuts`. A disagreement about `nuts=` versus `nuts_sampler_kwargs` is almost
always a version difference, and this turns two readings of the same source into two comparable
outputs. It will also show you if your venv has drifted out of the declared bounds, which is worth
checking before trusting a local test run.

`sqlite:///./genomeos.db` is the local default; production requires a PostgreSQL `DATABASE_URL`.
GCP operations must go through the [repository-local gcloud wrapper](docs/repo-gcloud-auth.md) —
never bare `gcloud`.

## Mandatory smoke and privacy gates

- Run `python scripts/smoke.py` after every code, configuration, schema, dependency, or runtime
  change. Run the focused tests for the touched behavior as well. Before a PR, also run the full CI
  commands above. Never claim completion without reporting exactly what ran.
- Before every commit and push, run `python scripts/check_private_files.py`. Inspect staged paths
  with `git diff --cached --name-only`; an ignored file is not proof that it was never force-added.
- Never commit or upload `.codex/`, `.agents/`, real `.env` files, auth/session/history stores,
  credentials, tokens, API keys, private keys, cloud service-account files, personal caches, or
  generated data containing restricted information. This applies to every branch and the full Git
  history, not only `main`.
- Only `.env.example`-style templates with obvious placeholders may be tracked. Examples must never
  contain a usable endpoint credential, account token, or personal secret.
- If private material is staged or committed, stop. Do not push. Remove it from the index and, if it
  entered any commit, rotate the credential and clean the affected history before continuing.

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
- **State the issues the PR closes explicitly, repeating the keyword for each one:**
  `Closes #14, closes #15, closes #16`. This is GitHub's documented syntax — a bare comma list
  like `Closes #14, #15` links only #14 in the PR's linked-issues panel.
- **Put a `closes #N` in the commit message too**, on the commit that does the work. This is the
  more reliable half: a squash merge concatenates the commit messages, so per-commit keywords
  reach the merge commit even when the PR body's linking was incomplete. One commit per issue
  makes this automatic.
- If a PR *advances* an issue without finishing it, say so in words instead, so it is not
  auto-closed.
- Say which design sections you implemented.
- State what you verified and how. If a test fails or you skipped part of the scope, say so
  plainly with the output — an unverified claim of completion is worse than an honest partial.
- **Show the map.** Once a change affects something renderable — observations, a surface, a
  mask, a burden layer — put a figure in the PR or issue rather than describing it. Generate it
  with a script under `scripts/plot_*.py`, commit the PNG under `docs/figures/`, and embed it
  with a raw URL (`https://raw.githubusercontent.com/bschilder/genomeOS/main/docs/figures/...`).
  A committed figure is reviewable, diffable and regenerable; a pasted screenshot is none of those.
- **Review figures obey the same invariants as the product.** Never draw a fitted surface and
  measured observations as one layer (§4), always show where there is no data rather than
  leaving it blank, and check the colour ramp reads low-to-high without the legend — a reversed
  ramp inverts the meaning of the map for anyone who only glances at it.
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

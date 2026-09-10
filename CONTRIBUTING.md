# Contributing to genomeOS

This file only routes you. The rules live in [`AGENTS.md`](AGENTS.md), which is the contract for
every contributor, human or agent. **Read it before writing code.** It is short on purpose.

## Start here

1. **[`AGENTS.md`](AGENTS.md)** — invariants, module boundaries, mandatory gates, PR rules.
   The section titled *Deliberate behaviours — do not "fix" these* will save you a wasted PR.
2. **[`docs/overview.md`](docs/overview.md)** — what the project is and why. It also lists what is
   deliberately **out** of scope for v1 (P6–P12); their absence is a decision, not an oversight.
3. **The doc for your workstream**, then the plan it links:

   | If you are touching | Read |
   |---|---|
   | Publication / literature evidence | [`docs/literature-evidence-curation.md`](docs/literature-evidence-curation.md) |
   | Data ingestion of any source | [Issue #3](https://github.com/bschilder/genomeOS/issues/3) — what every source is for and its access terms |
   | The Pan-UKB evidence slice | [`docs/panukb-architecture.md`](docs/panukb-architecture.md) |
   | The population registry, observations, surfaces, burden | [`docs/scientific-engineering-objectives.md`](docs/scientific-engineering-objectives.md) |
   | The board, labels, or status | [`docs/board-conventions.md`](docs/board-conventions.md) |

## Check the issues first — open *and* closed

The [issue tracker](https://github.com/bschilder/genomeOS/issues) is the record of what has been
done, what was decided, and why.

```bash
gh issue list --state all --search "your topic here"
```

Closed as *completed* means the work exists — read it rather than redoing it. Closed as *not
planned* means it was considered and rejected; reopening that needs an argument in the issue, not a
fresh PR. **If what you are about to do has no issue, that is a signal**: either you have found a
genuine gap, so file it, or the work is out of scope.

Status `Ready` means fully specified and unblocked. Take it without asking.

## Before you open a pull request

Run every gate. The PR template lists them, and CI runs the same set.

```bash
python -m pip install -e '.[dev,atlas,surfaces,geo,figures]'
ruff check .
python scripts/freeze_contract.py --check
python scripts/check_module_size.py
python scripts/check_private_files.py
python scripts/smoke.py
pytest
```

If you changed a schema, run `python scripts/freeze_contract.py` and commit the `contract/` diff.
That diff is the review surface for schema change, and CI fails if it is stale.

**Say what you ran and what happened.** A partial result reported honestly is worth more than an
unverified claim of completion. If a test fails or you skipped part of the scope, say so with the
output.

## Submitting data

Data contributions have a stricter bar than code, because a wrong number is harder to detect than a
broken build and can be cited before anyone notices.

- **Use the existing tools.** Discovery for a literature corpus goes through
  `scripts/fetch_pubmed_manifest.py`; do not write your own fetcher. Check `scripts/` before
  building anything that captures or transcribes a source.
- **Missing is a valid state.** Never invent, estimate, borrow, interpolate, or pick a
  "conservative" value for a field the source does not give you. Refusal is a valid output.
- **The extractor cannot be its own verifier.** Automated and LLM output is always
  `automated_proposal` / `pending`.
- **Geography comes only from an exact P0 alias** and its reviewed `uncertainty_radius_km`. Never
  copy a paper's country or coordinates into an evidence ledger.
- **Record source terms.** A completed check finding no explicit restriction is
  `no_restriction_found`; a check that did not happen is `not_checked`. The difference matters.

## Filing work

**Found a bug?** Open an issue with what you ran, what happened, and what you expected. If it
breaks one of the invariants in `AGENTS.md`, say which.

**Want a new feature?** Open an issue first and let it be triaged. Do not arrive with an unrequested
feature PR — priority here is derived from the dependency graph, so unscheduled work displaces
critical-path work even when it is a good idea.

**Improving the science?** Very welcome. Comment on the relevant issue or open a new one. The
dataset scores in [#3](https://github.com/bschilder/genomeOS/issues/3) and the statistics are both
fair game.

Apply the four label families (`type:*`, `P*:`, `skill:*`, `priority:*`) if you can. If you cannot —
you may not have triage rights on this repo — say so in the issue body so it can be triaged.

## Two labels worth knowing

- `wants-expert-review` — an agent implements it, a domain expert reviews after. Say explicitly in
  the PR what an expert should check.
- `needs-human-decision` — a person must commit on the project's behalf. **Do not decide it
  yourself.** Surface the options and stop.

## Definition of done

For the Atlas, correctness means **reproducing published science**, not producing plausible output.
Golden tests 1–3 gate publication of every other variant's burden layer. Never weaken a golden test
to make a build pass; if it fails, the pipeline is wrong.

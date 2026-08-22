# Board conventions

The [Genome OS Atlas project board](https://github.com/users/bschilder/projects/8) tracks all
work. Every issue carries four labels and four board fields.

## Labels

| Family | Values | Why |
|---|---|---|
| `type:*` | `data` `science` `infra` `ui` `docs` `governance` `outreach` | GitHub's native issue *types* are an organisation-only feature, so types are labels here. They group and filter identically on the board. |
| `P*:` | `P0:registry` `P1:observations` `P2:surfaces` `P3:burden` `P4:backend` `P5:map-ui` `launch` | Which sub-project of the [design spec](superpowers/specs/2026-08-22-genome-os-atlas-v1-design.md). |
| `skill:*` | `spatial-stats` `popgen` `clinical-genetics` `data-engineering` `frontend` `geospatial` `governance` `partnerships` | So an incoming contributor can filter to what they can actually do. |
| `priority:*` | `critical` `high` `medium` `low` | See below. |
| `needs-owner` | — | Nobody on the team currently has the skill this issue requires. |

## Priority semantics

Priority is derived from the **dependency graph**, not from enthusiasm. It answers "what breaks
if this is late", not "what would be nice".

- **critical** — blocks other work, or *is* the definition of done. Twelve issues. Examples: the
  registry schema (blocks every P0 adapter), the INLA-SPDE runtime decision (blocks all of P2),
  the MAP survey adapter (without it `β_design` is unidentifiable, so P2 cannot start), and
  golden test 1 (HbS parity — spec §8's definition of done).
- **high** — the milestone is meaningless without it.
- **medium** — wanted for the milestone.
- **low** — safe to defer.

## Board fields

**Status** — `Backlog` · `Ready` · `In progress` · `In review` · `Blocked` · `Done` ·
`Not planned`. `Ready` means fully specified with code in the plan and unblocked — pick one up
without asking. `Blocked` is set automatically for `needs-owner` issues.

**Sub-project**, **Skill**, **Priority** mirror the labels so the board can group and sort by
them. **Estimate** is a free number field, unset by default.

**Sub-issues progress** is native: each parent issue shows a completion bar over its children.

## Milestones

Mapped to **release boundaries rather than to P0–P5**, deliberately — sub-project is already
encoded in both a label and a board field, so a third copy would carry no information. Release
boundaries instead give each milestone a progress bar that answers a real question:

| Milestone | Covers | Answers |
|---|---|---|
| M1 — Data foundation | P0 + P1 | Does every observation have a coordinate and a known ascertainment design? |
| M2 — HbS parity | P2 + P3 | Can we reproduce Piel et al.'s published national estimates? |
| M3 — Map mode | P4 + P5 | Can someone open a browser and use it? |
| M4 — Public launch | governance track | Is it safe and legible to open to outside contributors? |

Milestones are assigned to **both** parents and sub-issues, since milestone progress counts
issues rather than hierarchy.

## Automation

`.github/workflows/project-status.yml` sets board Status on issue close and reopen. It exists
because GitHub's built-in "Item closed" workflow sets a single Status value and therefore cannot
distinguish an issue closed as *completed* from one closed as *not planned*. This reads
`state_reason` and routes to `Done` or `Not planned`; reopening routes to `In progress`.

Configuration lives in repository variables (`PROJECT_ID`, `STATUS_FIELD_ID`, `DONE_OPTION_ID`,
`NOT_PLANNED_OPTION_ID`, `IN_PROGRESS_OPTION_ID`), already set. It needs one secret:

```bash
# Classic token — NOT fine-grained. See below.
# github.com/settings/tokens -> "Tokens (classic)" -> scopes: repo + project
gh secret set PROJECT_TOKEN -R bschilder/genomeOS
```

**It must be a classic PAT.** Two separate limitations stack here:

1. The default `GITHUB_TOKEN` cannot write to user-owned Projects v2 at all.
2. **Fine-grained PATs cannot access Projects owned by a user account.** The `Projects`
   permission on fine-grained tokens is *organisation*-only — there is no equivalent checkbox
   for user-owned projects, so no fine-grained token can be configured to work here. This is a
   documented gap, not a misconfiguration.

Scopes needed on the classic token: **`project`** (the mutation) and **`repo`** (reading the
issue's `projectItems` connection — required because this repository is private).

If we later move the repo and project to an organisation, a fine-grained token scoped to that
org's `Projects: Read and write` becomes viable and would be the better choice.

## Two manual steps

1. **Set the secret above** — the workflow no-ops without it.
2. **Set the board's sort.** Open the board view → *Group by* `Status` → *Sort by* `Priority`
   ascending (Critical first). Projects v2 view configuration — grouping and sorting — is not
   writable through the API, so this is a one-time UI step.

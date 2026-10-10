# Board conventions

The [Genome OS Atlas project board](https://github.com/orgs/genomeOS/projects/1) tracks all
work. Every issue carries four labels and four board fields.

## Labels

| Family | Values | Why |
|---|---|---|
| `type:*` | `data` `science` `infra` `ui` `docs` `governance` `outreach` | The repository began under a personal account, where GitHub's native issue *types* are not available, so types are labels here. They group and filter identically on the board. |
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

`.github/workflows/project-status.yml` does two jobs that GitHub's built-in project workflows
cannot, both of which are UI-only to configure and therefore easy to lose:

- **`add-to-project`** — puts every newly opened issue on the board as `Backlog`. The built-in
  "Auto-add to project" workflow cannot be enabled through the API at all, so doing it here keeps
  it in version control.
- **`set-status`** — routes closes and reopens. The built-in "Item closed" workflow sets a single
  Status value and therefore cannot distinguish an issue closed as *completed* from one closed as
  *not planned*. This reads `state_reason` → `Done` / `Not planned`; reopening → `In progress`.

Verified end to end: close-as-not-planned → `Not planned`, reopen → `In progress`,
close-as-completed → `Done`, new issue → on the board as `Backlog`.

Configuration lives in repository variables (`PROJECT_ID`, `STATUS_FIELD_ID`,
`BACKLOG_OPTION_ID`, `DONE_OPTION_ID`, `NOT_PLANNED_OPTION_ID`, `IN_PROGRESS_OPTION_ID`),
already set for the organisation board. It needs one secret, `PROJECT_TOKEN`, also set:

```bash
gh secret set PROJECT_TOKEN -R genomeOS/genomeOS
```

The default `GITHUB_TOKEN` cannot write to Projects v2, so the workflow needs a personal access
token. The current secret is a classic PAT with the **`project`** and **`repo`** scopes. It dates
from when the board was owned by a user account, where fine-grained tokens cannot reach Projects
at all. It kept working after the board moved to the organisation on 2026-10-10 (#425).

When the token is next rotated, prefer a fine-grained token with **genomeOS** as the resource
owner, organisation permission **`Projects: Read and write`**, and repository access to
`genomeOS/genomeOS` with **`Issues: Read`**. The board belongs to the organisation now, so the
fine-grained route is available.

## One manual step

**Set the board's sort.** Open the board view → *Group by* `Status` → *Sort by* `Priority`
ascending (Critical first). Projects v2 view configuration — grouping and sorting — is not
writable through the API, so this is the one thing that has to be done in the UI.

(The `PROJECT_TOKEN` secret is set, and auto-add is handled by the workflow above rather than by
the UI-only built-in.)

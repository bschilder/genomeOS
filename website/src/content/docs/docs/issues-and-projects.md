---
title: Issues and Projects
description: How genomeOS turns ideas into Ready issues, reviewable pull requests, and truthful project status.
sidebar:
  order: 6
---

GitHub Issues record both work and decisions. The
[project board](https://github.com/users/bschilder/projects/8) shows how that work moves.

## Before starting

1. Introduce yourself in [Discussion #76](https://github.com/bschilder/genomeOS/discussions/76).
2. Search [open and closed issues](https://github.com/bschilder/genomeOS/issues?q=is%3Aissue).
3. Choose an issue marked `Ready`, or open a scoped issue for triage.
4. State objective, acceptance evidence, public interface, assumptions, refusal conditions, and downstream consumers.
5. Work on a branch and open a pull request; never commit directly to `main`.

When posting a substantive issue update, mention the original issue author so they receive the
context they asked for.

## Labels and status

Every issue carries `type:*`, `P*:`, `skill:*`, and `priority:*` labels. Priority follows the
dependency graph. `Ready` means fully specified and unblocked. `needs-human-decision` means an
agent must present the choice and stop. `wants-expert-review` means implementation can proceed but
the pull request must name what an expert should evaluate.

Read the complete [board conventions](https://github.com/bschilder/genomeOS/blob/main/docs/board-conventions.md)
and [contribution guide](../../contribute/).

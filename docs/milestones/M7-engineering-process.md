---
id: M7-engineering-process
title: M7 — Engineering process
type: milestone
status: current
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# M7 — Engineering process

**Open.** Started 2026-07-31. No Jira epic — this milestone *is* the record-keeping work.

## Goal

Move from POC record-keeping to a real engineering record, and make the repo meet the standards it enforces
on others.

## Delivered (2026-07-31)

- The work ledger: `AGENTS.md`, `PLAN.md`, `docs/{architecture,decisions,plans,milestones,tasks,bugs,notes}`
  ([ADR-0034])
- 34 ADRs reverse-engineered from git history and the RHAIFIRST-168 tree
- 12 architecture documents, including the nine-state machine and the artifact contracts — neither of which
  existed in any form
- `FOREDER.md` recovered from `3bd2d3e^` and tracked
- A real README for `epic-code-gen-pipeline`, replacing GitLab boilerplate
- The PR companion rule, a PR template, `scripts/check_ledger.py`, and the repo's first CI

## Still open

The debt this exercise surfaced was documented rather than fixed, deliberately — see
[[bug-repo-does-not-meet-own-standards]] and `docs/tasks/pending/`. Highest priority:

- No lint or type check on 10.5k lines of Python
- `jira_utils.py` (1,055 lines), `frontmatter.py`, `state.py`, `parse_prototype.js` — zero tests
- `rubrics/` deletion
- Flip `check_ledger.py --diff` from advisory to blocking

---
id: task-rebase-epic-branches-every-cycle
title: Rebase epic branches onto upstream base every review-response cycle
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-376
commits: ["164d21e"]
decisions: [ADR-0031]
---

# Task: Rebase epic branches onto upstream base every review-response cycle

## Goal

Keep PRs mergeable and author fixes against current upstream code.

## Context

Because progress happens one step per run and PRs wait on humans, a branch can sit for days while upstream moves. PRs drifted into CONFLICTING, and fixes were written against stale code.

## Acceptance Criteria

- [x] Rebase runs at the start of every review-response cycle
- [x] `rebase_onto_base()` drives the git sequence; a subagent edits only the working tree
- [x] Result pushed with `--force-with-lease`, never a plain force
- [x] A cycle that rebases nothing and finds nothing actionable does not consume an iteration

## Files Likely Involved

- `scripts/rebase_pr.py`
- `scripts/review_response.py`
- `tests/test_rebase_pr.py`

## Status

Done.

## Notes

Verified: `--force-with-lease` at `rebase_pr.py:233`. `MAX_CONFLICT_ROUNDS = 10`, `CONFLICT_AGENT_TIMEOUT = 900` — both plain constants, not env-tunable, unlike the two review-response timeouts. The same commit also fixed RHAIFIRST-375.

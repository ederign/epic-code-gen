---
id: bug-max-iterations-default-disagrees
title: max_iterations defaults to 3 in one code path and 10 in five others
type: bug
status: open
repos: [epic-code-gen]
decisions: [ADR-0033]
---

# Bug: max_iterations defaults to 3 in one code path and 10 in five others

## Summary

An epic whose state file predates the `max_iterations` field gets a budget of 3 in the scoring path and 10 everywhere else.

## Reproduction

1. Create an epic state file without a `max_iterations` key.
2. Drive it to `ReviewPending`.
3. Observe `_ci_handle_review_pending` treating the budget as 3 while the PR path treats it as 10.

## Expected

One default, defined once.

## Actual

`run_pipeline.py:1375` — `max_iter = state.get("max_iterations", 3)`. Five other sites use 10: `_init_epic_state` (`:1201`), `_ci_handle_pr_changes` (`:1502`), `review_cycle.py:356`, `SKILL.md:104`, `artifact_utils.py:274`. `README.md` still documents 3.

## Impact

Medium

## Evidence

The value decides when an epic is declared exhausted and whether a near-miss PR opens, so the disagreement is not cosmetic: the same epic can be 'exhausted' in one handler and have budget remaining in another.

## Related Tasks

- [[task-triage-memory-and-oscillation]]
- [[bug-readme-is-stale]]
- Fix: a single module-level constant in `artifact_utils.py`, referenced everywhere

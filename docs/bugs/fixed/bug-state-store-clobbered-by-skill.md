---
id: bug-state-store-clobbered-by-skill
title: Pipeline state store clobbered by the skill; invalid 'completed' status deadlocks strategies
type: bug
status: fixed
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-374
commits: ["e03689c", "3bbcd2d"]
decisions: [ADR-0013, ADR-0014, ADR-0015]
---

# Bug: Pipeline state store clobbered by the skill; invalid 'completed' status deadlocks strategies

## Summary

`run-metadata.yaml` was written by two producers with incompatible schemas, and the second write destroyed the first. The skill set `status: completed`, which is not a member of `CI_STATES`, so the CI dispatcher fell through every branch to `else` and returned `SKIPPED … "Unknown state: completed"` — while exiting 0.

## Reproduction

1. Run a strategy through to a completed codegen for one epic.
2. Let `/epic-codegen` write its run summary over `run-metadata.yaml`.
3. Re-run the pipeline for the same strategy.
4. Observe the epic reported as skipped, and any epic depending on it stuck at Blocked.

## Expected

The epic advances to `ReviewPending` or `PRCreated`, and its dependents unblock when it reaches `Done`.

## Actual

The epic is skipped on **every** subsequent run, forever. Dependents stay Blocked indefinitely. The job exits 0 and reports success — a silent deadlock.

## Impact

Critical

## Observed incident

RHAISTRAT-2162, 2026-07-28/29. RHAI-74 (PR ederign/kale#11, score 9.4, verdict pass) and RHAI-76 (#12, 8.6) were both left at `status: completed`. Subsequent runs reported `0 processed, 2 skipped, 3 blocked` in ~118s. RHAI-75 was blocked by 74, RHAI-78 by 75, and RHAI-77 by all four, so the entire strategy deadlocked with two merge-quality PRs stranded and no error surfaced anywhere.

## Evidence

**Three competing vocabularies for one field:**

- `run_pipeline.py` `CI_STATES`: Pending, Ready, Generating, ReviewPending, PRCreated, PRChangesRequested, Done, Blocked, Failed
- `SKILL.md`: `completed|exhausted|failed|error` (lowercase)
- `artifact_utils.py` codegen-run enum: Running, Completed, Failed, Exhausted (capitalised)

**Fields silently dropped** by the skill's whole-file write — from RHAI-74: `current_version`, `max_iterations`, `pr_state`, `timestamps`, `scores`. RHAI-76 also lost `strategy_key` and `target_branch`, and used a *third* field layout (`scores_by_dimension`, `pr_note`, `started_at`/`completed_at`) — the skill's output was not self-consistent between two epics in the same run.

## Related Tasks

- [[task-ci-state-machine-and-convergence]]
- [[M5-state-integrity]]
- Fix: one owner per status field ([ADR-0013]), merge-never-write ([ADR-0014]), normalize-on-read and fail loudly ([ADR-0015])
- Residue: `RHAISTRAT-2352/RHAI-264` still carries the corrupt value, rescued on read rather than migrated

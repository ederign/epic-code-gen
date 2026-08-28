---
id: task-ci-state-machine-and-convergence
title: run_pipeline.py CI adaptation — state machine and convergence
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-203
commits: ["c98dbbc", "80f81ad", "2e59f0c"]
decisions: [ADR-0009, ADR-0013]
---

# Task: run_pipeline.py CI adaptation — state machine and convergence

## Goal

A nine-state machine that advances each epic exactly one step per run.

## Context

An epic's journey depends on humans reviewing PRs. A job that blocks on humans for days is not a job, so progress must happen across runs.

## Acceptance Criteria

- [x] Nine states with one action per epic per run
- [x] Runs are idempotent — safe to re-trigger
- [x] A no-op is a successful outcome, with telemetry still recorded
- [x] Blocked is not terminal
- [x] 15 tests

## Files Likely Involved

- `scripts/run_pipeline.py`
- `scripts/artifact_utils.py`
- `tests/test_ci_mode.py`

## Status

Done.

## Notes

The transition graph lived only as `if/elif` until `docs/architecture/02-pipeline-state-machine.md`. Its unknown-state branch was a silent `SKIPPED` that exited 0 — the RHAIFIRST-374 deadlock. Fixed by [ADR-0015].

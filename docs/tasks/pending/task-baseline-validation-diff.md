---
id: task-baseline-validation-diff
title: Capture a baseline validation run and diff findings against it
type: task
status: pending
repos: [epic-code-gen]
jira: RHAIFIRST-392
decisions: [ADR-0025]
---

# Task: Capture a baseline validation run and diff findings against it

## Goal

Attribute check failures to the epic only when the epic caused them.

## Context

A target repo whose `make lint` is red on `main` fails every epic generated against it, and because GNU make stops at the first failing prerequisite, the baseline failure also conceals genuine findings. See [[bug-baseline-check-failures-scored-as-epic]].

## Acceptance Criteria

- [ ] Run validation at `BASE_SHA` before generating, and store the result
- [ ] Diff post-generation findings against the baseline; only new findings are the epic's
- [ ] Baseline failures reported distinctly — like `unrunnable`, not as `failed`
- [ ] Handle the make short-circuit so later sub-targets still run
- [ ] The repo readiness assessment should probably fail a repo that is red on `main`

## Files Likely Involved

- `scripts/validate_target.py`
- `scripts/run_pipeline.py`
- `.claude/agents/lint-reviewer.md`

## Status

Pending.

## Notes

The cleanest framing is that this extends [ADR-0025]'s three-state model to a fourth: `passed` / `failed` / `unrunnable` / `pre-existing`. The make short-circuit is the harder half — running sub-targets individually rather than the aggregate target would solve it but diverges from 'run what the repo runs'.

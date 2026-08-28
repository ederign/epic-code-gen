---
id: task-investigate-max-turns
title: Investigate and configure --max-turns for Claude CLI codegen runs
type: task
status: pending
repos: [epic-code-gen, epic-code-gen-pipeline]
jira: RHAIFIRST-195
---

# Task: Investigate and configure --max-turns for Claude CLI codegen runs

## Goal

Decide whether a turn ceiling is a useful guard against runaway sessions.

## Context

A codegen session is bounded by wall-clock timeout (6h) and iteration budget (10), but not by turns. A session can burn its budget in a loop that makes no progress.

## Acceptance Criteria

- [ ] Determine whether `--max-turns` interacts safely with SDD and the review loop
- [ ] Pick a value with evidence, or record why not to use it

## Files Likely Involved

- `ci-scripts/run-claude.sh`

## Status

Pending.

## Notes

Linked as Related to RHAIFIRST-168 rather than a child. Consider alongside an early-abandon heuristic on a flat score progression — see [ADR-0033]'s negative consequences.

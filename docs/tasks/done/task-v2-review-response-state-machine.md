---
id: task-v2-review-response-state-machine
title: V2 review response — state machine integration
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-212
commits: ["6aecf9b", "48185b8", "7f4c35f"]
decisions: [ADR-0032]
---

# Task: V2 review response — state machine integration

## Goal

Wire the review-response loop into the CI state machine.

## Context

Regenerating a branch under review throws away reviewer effort and makes the PR's history useless. Fixes must land as commits on top of the existing branch.

## Acceptance Criteria

- [x] Existing branch checked out from the fork, never regenerated
- [x] Humans always addressed; bots selectively
- [x] Only code inside our own diff is touched
- [x] Every comment replied to, processed IDs recorded

## Files Likely Involved

- `scripts/run_pipeline.py`
- `tests/test_review_response.py`

## Status

Done.

## Notes

`_ci_handle_pr_changes` was rewritten for this. `48185b8` fixed six issues found in this work's own review before merge — the process working as intended. 66 tests.

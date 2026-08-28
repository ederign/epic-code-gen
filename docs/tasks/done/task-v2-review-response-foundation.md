---
id: task-v2-review-response-foundation
title: V2 review response — foundation utilities
type: task
status: done
repos: [epic-code-gen]
jira: RHAIFIRST-212
commits: ["99c9bc6"]
decisions: [ADR-0032]
---

# Task: V2 review response — foundation utilities

## Goal

Primitives for reading PR state and triaging review comments.

## Context

Regenerating a branch under review throws away reviewer effort and makes the PR's history useless. Fixes must land as commits on top of the existing branch.

## Acceptance Criteria

- [x] Existing branch checked out from the fork, never regenerated
- [x] Humans always addressed; bots selectively
- [x] Only code inside our own diff is touched
- [x] Every comment replied to, processed IDs recorded

## Files Likely Involved

- `scripts/pr_lifecycle.py`
- `scripts/github_utils.py`
- `scripts/clone_target.py`

## Status

Done.

## Notes

`compute_diff_scope` / `is_comment_in_scope` are what keep a reviewer's aside about unrelated code from becoming a refactor. `checkout_existing_branch` is the entry point that makes commit-on-top possible.

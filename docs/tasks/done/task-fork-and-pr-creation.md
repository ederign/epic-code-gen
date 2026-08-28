---
id: task-fork-and-pr-creation
title: Fork creation, push-to-fork, and PR creation for CI
type: task
status: done
repos: [epic-code-gen]
commits: ["a0de047", "2cfab1e", "5d7c799", "addaaa3", "4169f06", "19abb33"]
decisions: [ADR-0030]
---

# Task: Fork creation, push-to-fork, and PR creation for CI

## Goal

Open PRs on other teams' repos without write access, under an unambiguous bot identity.

## Context

Target repos belong to other teams. The pipeline has no write access, and a PR that appears to come from a human misrepresents its authorship.

## Acceptance Criteria

- [x] Fork created if absent, synced and upstream-fetched before branching
- [x] Branch `epic/<EPIC_ID>`
- [x] Git identity derived from the token
- [x] Default fork owner `dora-the-ai-coder`
- [x] Target repo's own PR template and detected default branch used
- [x] Token-embedded URLs sanitized from error output

## Files Likely Involved

- `scripts/clone_target.py`
- `scripts/push_to_fork.py`
- `scripts/create_pr.py`
- `scripts/github_utils.py`

## Status

Done.

## Notes

Nine real PRs across seven repos, five merged. Using the target's own PR template makes the PR read as a native contribution rather than an automated dump.

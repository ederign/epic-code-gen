---
id: task-triage-memory-and-oscillation
title: History-aware triage with accepted-findings carry-forward
type: task
status: done
repos: [epic-code-gen]
commits: ["cf1da6e", "050732f", "24d8078", "8a4a5c7", "0aa99e8"]
decisions: [ADR-0033]
---

# Task: History-aware triage with accepted-findings carry-forward

## Goal

Stop triage relitigating findings it already dismissed, and stop fixes oscillating between dimensions.

## Context

Reviewers are not perfectly consistent between versions. Scores were plateauing while findings rotated: a fix for one dimension created a finding in another, and triage revisited findings it had already dismissed with reason.

## Acceptance Criteria

- [x] Findings dismissed with a reason carried forward in `tmp/accepted-findings-<EPIC>.json`
- [x] Triage reads prior versions' decisions
- [x] Cross-dimension dedup
- [x] Fix work batched: apply all fixes, then test and commit once
- [x] Fix loop runs in a fresh-context subagent

## Files Likely Involved

- `.claude/agents/iteration-reviewer.md`
- `scripts/review_cycle.py`

## Status

Done.

## Notes

Decisions are recorded in `decision-log.md` per version, so triage is auditable. `8a4a5c7` moving the loop to a fresh context matters because triage quality degrades badly under context pressure.

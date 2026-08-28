---
id: task-context-compaction-recovery
title: Survive context compaction with a SessionStart hook
type: task
status: done
repos: [epic-code-gen]
commits: ["7848b5e"]
decisions: [ADR-0004]
---

# Task: Survive context compaction with a SessionStart hook

## Goal

Make a compaction a non-event for a run in progress.

## Context

A single epic run is up to 6 hours with 10 iterations, so it will be compacted. Before this, a compaction mid-review restarted the loop or silently skipped it.

## Acceptance Criteria

- [x] State persisted to `tmp/epic-codegen-<EPIC>.json`
- [x] `SessionStart` hook with `matcher: compact` runs `review_cycle.py dispatch-context`
- [x] Loop state reprinted when phase is review / fixing / implementing
- [x] Filesystem polling for subagent completion removed

## Files Likely Involved

- `.claude/settings.json`
- `scripts/review_cycle.py`
- `scripts/state.py`

## Status

Done.

## Notes

This is the difference between a 6-hour run completing and producing nothing. `state.py` is explicitly non-atomic while `review_cycle.py` reads it from a parallel dispatch loop, and has no tests — [[bug-state-py-is-non-atomic]].

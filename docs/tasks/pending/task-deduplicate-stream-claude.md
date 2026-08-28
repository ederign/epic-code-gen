---
id: task-deduplicate-stream-claude
title: Deduplicate stream-claude.py across the two repos
type: task
status: pending
repos: [epic-code-gen, epic-code-gen-pipeline]
---

# Task: Deduplicate stream-claude.py across the two repos

## Goal

One copy of the stream renderer.

## Context

`stream-claude.py` exists in both `epic-code-gen/ci-scripts/` and `epic-code-gen-pipeline/ci-scripts/` — two copies, no shared source, free to diverge. Only the `epic-code-gen` copy is actually invoked at runtime (by `run-claude.sh`).

## Acceptance Criteria

- [ ] Confirm which copy is live and whether they have diverged
- [ ] Delete the unused copy
- [ ] If both are needed, document why (as [ADR-0014] does for the merge logic)

## Files Likely Involved

- `ci-scripts/stream-claude.py`

## Status

Pending.

## Notes

The pipeline repo's copy appears vestigial since [ADR-0012] — the orchestrator is invoked directly there, and the inner Claude session is wrapped by `epic-code-gen`'s copy. Diff them first; a silent divergence would explain any renderer inconsistency between environments.

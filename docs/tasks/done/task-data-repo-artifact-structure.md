---
id: task-data-repo-artifact-structure
title: epic-code-gen-pipeline-data repo — artifact structure and push-results
type: task
status: done
repos: [epic-code-gen, epic-code-gen-pipeline, epic-code-gen-pipeline-data]
jira: RHAIFIRST-204
commits: ["d5fd44a", "cf16af6", "f46bf4a"]
decisions: [ADR-0008]
---

# Task: epic-code-gen-pipeline-data repo — artifact structure and push-results

## Goal

Durable per-epic state and artifacts in a git repo the dashboard can just clone.

## Context

The CI container is discarded after every job, so state must live somewhere else. Jira cannot hold diffs and review documents without becoming unreadable.

## Acceptance Criteria

- [x] strategy / epic / version directory layout
- [x] Append-only `run-log.jsonl` per strategy
- [x] `run-metadata.yaml` as the state file the pipeline reads
- [x] Diffs only, never full source files
- [x] Versions accumulate, never deleted

## Files Likely Involved

- `ci-scripts/push-results.py`
- `tests/test_push_results.py`

## Status

Done.

## Notes

Now 33 MB for 24 epics, 13.7 MB of it three OTEL files. No pruning strategy — predicted in `FOREDER.md`, tracked as [[task-prune-data-repo-growth]]. The two-writer problem on `run-metadata.yaml` originates here.
